"""A leading ``x_`` on a raw filename is the same run when the size matches."""

from __future__ import annotations

import dataclasses
import os
from pathlib import Path

from metabwatch.pipeline import run_watch_mode
from metabwatch.presets import build_pipeline_config
from metabwatch.processor.orchestrator import ProcessResult, ProcessorOrchestrator
from metabwatch.state.manifest_store import ManifestStateStore

_POLARITY_MISMATCH = (
    "Polarity mismatch: file neg.raw is 'negative' "
    "but this run is locked to 'positive'."
)


def _complete(store: ManifestStateStore, path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    store.mark_in_progress(path)
    store.mark_completed(
        path,
        path.with_suffix(".csv"),
        path.with_suffix(".trace.csv"),
    )


def _store(tmp_path: Path) -> ManifestStateStore:
    return ManifestStateStore(tmp_path / "pipeline_manifest.json")


def test_other_spelling_peels_one_x_prefix(tmp_path: Path) -> None:
    folder = tmp_path / "raw"
    assert ManifestStateStore.other_spelling(folder / "Foo.raw") == folder / "x_Foo.raw"
    assert ManifestStateStore.other_spelling(folder / "x_Foo.raw") == folder / "Foo.raw"
    assert (
        ManifestStateStore.other_spelling(folder / "x_x_Foo.raw")
        == folder / "x_Foo.raw"
    )
    assert ManifestStateStore.other_spelling(folder / "x_.raw") is None


def test_completed_file_blocks_same_size_x_prefix(tmp_path: Path) -> None:
    store = _store(tmp_path)
    original = tmp_path / "Foo.raw"
    renamed = tmp_path / "x_Foo.raw"
    _complete(store, original, b"same")
    renamed.write_bytes(b"same")
    os.utime(renamed, (1_700_000_000, 1_800_000_000))

    assert store.should_process(renamed) is False
    assert store.same_run_block(renamed) == original.resolve()


def test_completed_x_prefix_blocks_the_unprefixed_name(tmp_path: Path) -> None:
    store = _store(tmp_path)
    renamed = tmp_path / "x_Foo.raw"
    original = tmp_path / "Foo.raw"
    _complete(store, renamed, b"same")
    original.write_bytes(b"same")

    assert store.should_process(original) is False
    assert store.same_run_block(original) == renamed.resolve()


def test_different_size_directory_or_prefix_still_processes(tmp_path: Path) -> None:
    store = _store(tmp_path)
    original = tmp_path / "Foo.raw"
    _complete(store, original, b"same")

    different_size = tmp_path / "x_Foo.raw"
    different_size.write_bytes(b"not-the-same-size")
    assert store.should_process(different_size) is True

    other_dir = tmp_path / "elsewhere"
    other_dir.mkdir()
    elsewhere = other_dir / "x_Foo.raw"
    elsewhere.write_bytes(b"same")
    assert store.should_process(elsewhere) is True

    upper = tmp_path / "X_Foo.raw"
    upper.write_bytes(b"same")
    assert store.should_process(upper) is True

    double = tmp_path / "x_x_Foo.raw"
    double.write_bytes(b"same")
    assert store.should_process(double) is True


def test_second_x_prefix_matches_the_once_prefixed_name(tmp_path: Path) -> None:
    store = _store(tmp_path)
    once = tmp_path / "x_Foo.raw"
    twice = tmp_path / "x_x_Foo.raw"
    _complete(store, once, b"same")
    twice.write_bytes(b"same")

    assert store.should_process(twice) is False


def test_retryable_failure_still_processes_the_renamed_file(tmp_path: Path) -> None:
    store = _store(tmp_path)
    original = tmp_path / "Foo.raw"
    renamed = tmp_path / "x_Foo.raw"
    original.write_bytes(b"same")
    store.mark_in_progress(original)
    store.mark_failed(original, "Failed to parse raw file")
    renamed.write_bytes(b"same")

    assert store.should_process(renamed) is True
    assert store.same_run_block(renamed) is None


def test_polarity_mismatch_blocks_the_other_spelling_until_size_changes(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    original = tmp_path / "Foo.raw"
    renamed = tmp_path / "x_Foo.raw"
    original.write_bytes(b"same")
    store.mark_in_progress(original)
    store.mark_failed(original, _POLARITY_MISMATCH)
    renamed.write_bytes(b"same")

    assert store.should_process(renamed) is False
    renamed.write_bytes(b"changed")
    assert store.should_process(renamed) is True


def test_in_progress_entry_blocks_the_other_spelling(tmp_path: Path) -> None:
    store = _store(tmp_path)
    original = tmp_path / "Foo.raw"
    renamed = tmp_path / "x_Foo.raw"
    original.write_bytes(b"same")
    store.mark_in_progress(original)
    renamed.write_bytes(b"same")

    assert store.should_process(renamed) is False


def test_same_path_modification_time_change_still_reprocesses(tmp_path: Path) -> None:
    store = _store(tmp_path)
    original = tmp_path / "Foo.raw"
    _complete(store, original, b"same")
    stat = original.stat()
    os.utime(original, (stat.st_atime, stat.st_mtime + 50))

    assert store.should_process(original) is True
    assert store.same_run_block(original) is None


def test_own_entry_wins_when_that_path_changes(tmp_path: Path) -> None:
    store = _store(tmp_path)
    original = tmp_path / "Foo.raw"
    renamed = tmp_path / "x_Foo.raw"
    _complete(store, original, b"aa")
    _complete(store, renamed, b"aa")
    renamed.write_bytes(b"bbb")

    assert store.should_process(renamed) is True


def _watch_config(tmp_path: Path):
    raw_dir = tmp_path / "raw"
    out_dir = tmp_path / "out"
    raw_dir.mkdir()
    out_dir.mkdir()
    config = build_pipeline_config(
        "hilic_metab_pnnl",
        "targeted",
        raw_dir,
        out_dir,
        polarity="positive",
    )
    config = dataclasses.replace(
        config,
        watcher=dataclasses.replace(
            config.watcher,
            poll_interval_sec=0.01,
            stability_wait_sec=0.0,
            discovery_mode="poll",
        ),
        initial_backoff_sec=0.0,
    )
    return config, raw_dir


def _stop_after(monkeypatch, polls: int) -> None:
    waits = {"n": 0}

    def _wait(_poll_interval_sec: float, _stop_event) -> bool:
        waits["n"] += 1
        return waits["n"] >= polls

    monkeypatch.setattr("metabwatch.pipeline._wait_for_poll", _wait)


def _patch_processor(monkeypatch, tmp_path: Path) -> list[str]:
    calls: list[str] = []

    def _ok(self, raw_file: Path, *, expected_polarity: str | None = None):
        calls.append(raw_file.name)
        return ProcessResult(
            raw_file=raw_file,
            status="completed",
            rows=1,
            targets=1,
            polarity="positive",
            output_csv=tmp_path / "matches.csv",
            trace_csv=tmp_path / "traces.csv",
        )

    monkeypatch.setattr(ProcessorOrchestrator, "process_single_raw", _ok)
    monkeypatch.setattr(
        "metabwatch.pipeline._run_synthesis",
        lambda *_args, **_kwargs: tmp_path / "dashboard.html",
    )
    return calls


def test_watch_processes_only_the_unprefixed_name_when_both_are_new(
    monkeypatch, tmp_path, capsys
) -> None:
    config, raw_dir = _watch_config(tmp_path)
    (raw_dir / "QC_Metab_01.raw").write_bytes(b"same")
    (raw_dir / "x_QC_Metab_01.raw").write_bytes(b"same")
    (raw_dir / "QC_Metab_02.raw").write_bytes(b"other")
    calls = _patch_processor(monkeypatch, tmp_path)

    assert run_watch_mode(config, once=True) == 0
    assert calls == ["QC_Metab_01.raw", "QC_Metab_02.raw"]
    skip = "Skipped x_QC_Metab_01.raw: same run as QC_Metab_01.raw"
    assert capsys.readouterr().out.count(skip) == 1


def test_watch_processes_both_names_when_sizes_differ(monkeypatch, tmp_path) -> None:
    config, raw_dir = _watch_config(tmp_path)
    (raw_dir / "QC_Metab_01.raw").write_bytes(b"a")
    (raw_dir / "x_QC_Metab_01.raw").write_bytes(b"bb")
    calls = _patch_processor(monkeypatch, tmp_path)

    assert run_watch_mode(config, once=True) == 0
    assert calls == ["QC_Metab_01.raw", "x_QC_Metab_01.raw"]


def test_watch_skips_recorded_run_after_x_rename_and_logs_once(
    monkeypatch, tmp_path, capsys
) -> None:
    config, raw_dir = _watch_config(tmp_path)
    original = raw_dir / "QC_Metab_01.raw"
    original.write_bytes(b"same")
    store = ManifestStateStore(config.state.pipeline_manifest)
    store.mark_in_progress(original)
    store.mark_completed(
        original,
        tmp_path / "matches.csv",
        tmp_path / "traces.csv",
        polarity="positive",
    )
    original.unlink()
    renamed = raw_dir / "x_QC_Metab_01.raw"
    renamed.write_bytes(b"same")
    os.utime(renamed, (1_700_000_000, 1_800_000_000))
    calls = _patch_processor(monkeypatch, tmp_path)
    _stop_after(monkeypatch, 3)

    assert run_watch_mode(config, once=False) == 0
    assert calls == []
    skip = "Skipped x_QC_Metab_01.raw: same run as QC_Metab_01.raw"
    assert capsys.readouterr().out.count(skip) == 1


def test_force_reprocess_runs_a_lone_x_file(monkeypatch, tmp_path, capsys) -> None:
    config, raw_dir = _watch_config(tmp_path)
    original = raw_dir / "QC_Metab_01.raw"
    original.write_bytes(b"same")
    store = ManifestStateStore(config.state.pipeline_manifest)
    store.mark_in_progress(original)
    store.mark_completed(
        original,
        tmp_path / "matches.csv",
        tmp_path / "traces.csv",
        polarity="positive",
    )
    original.unlink()
    (raw_dir / "x_QC_Metab_01.raw").write_bytes(b"same")
    calls = _patch_processor(monkeypatch, tmp_path)

    assert run_watch_mode(config, once=True, force_reprocess=True) == 0
    assert calls == ["x_QC_Metab_01.raw"]
    assert "same run as" not in capsys.readouterr().out


def test_force_reprocess_keeps_the_unprefixed_name_when_both_exist(
    monkeypatch, tmp_path
) -> None:
    config, raw_dir = _watch_config(tmp_path)
    (raw_dir / "QC_Metab_01.raw").write_bytes(b"same")
    (raw_dir / "x_QC_Metab_01.raw").write_bytes(b"same")
    calls = _patch_processor(monkeypatch, tmp_path)

    assert run_watch_mode(config, once=True, force_reprocess=True) == 0
    assert calls == ["QC_Metab_01.raw"]
