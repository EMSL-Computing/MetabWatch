"""Operator-facing watch/process log lines."""

from __future__ import annotations

import dataclasses
import threading
from pathlib import Path

from metabwatch.pipeline import (
    _announce_result,
    _clickable_path,
    _idle_message,
    _polarity_skip_line,
    _sample_result_line,
    run_watch_mode,
)
from metabwatch.presets import build_pipeline_config
from metabwatch.processor.orchestrator import ProcessResult, ProcessorOrchestrator


def _config(tmp_path: Path, *, polarity: str | None = None):
    raw_dir = tmp_path / "raw"
    out_dir = tmp_path / "out"
    raw_dir.mkdir()
    out_dir.mkdir()
    config = build_pipeline_config(
        "hilic_metab_pnnl",
        "targeted",
        raw_dir,
        out_dir,
        polarity=polarity,
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


def test_clickable_path_is_plain_when_stdout_is_not_a_terminal(monkeypatch, tmp_path) -> None:
    class _Out:
        def isatty(self) -> bool:
            return False

    monkeypatch.setattr("metabwatch.pipeline.sys.stdout", _Out())
    path = tmp_path / "dashboard.html"
    assert _clickable_path(path) == str(path.resolve())
    assert "\033" not in _clickable_path(path)


def test_clickable_path_is_a_link_on_a_terminal(monkeypatch, tmp_path) -> None:
    class _Out:
        def isatty(self) -> bool:
            return True

    monkeypatch.setattr("metabwatch.pipeline.sys.stdout", _Out())
    path = tmp_path / "dashboard.html"
    text = _clickable_path(path)
    assert text.startswith("\033]8;;file://")
    assert str(path.resolve()) in text
    assert text.endswith("\033]8;;\033\\")


def test_sample_result_line_includes_lock_only_when_this_file_locks() -> None:
    result = ProcessResult(
        raw_file=Path("QC_Metab_Neg-01.raw"),
        status="completed",
        rows=15,
        targets=15,
        polarity="negative",
    )
    assert _sample_result_line(result, locked=True) == (
        "  15 of 15 matched. Run locked to negative."
    )
    assert _sample_result_line(result, locked=False) == "  15 of 15 matched"
    bare = ProcessResult(raw_file=Path("a.raw"), status="completed", rows=3)
    assert _sample_result_line(bare, locked=False) == "  3 matched"


def test_polarity_skip_line_uses_the_file_and_lock() -> None:
    error = (
        "Polarity mismatch: file QC_Metab_Pos-02.raw is 'positive' "
        "but this run is locked to 'negative'. "
        "MetabWatch does not allow mixed polarities in one input folder / run."
    )
    assert _polarity_skip_line("QC_Metab_Pos-02.raw", error) == (
        "Skipped QC_Metab_Pos-02.raw — positive file; this run is negative"
    )


def test_announce_result_labels_a_real_failure(capsys) -> None:
    result = ProcessResult(
        raw_file=Path("QC_Metab_Neg-01.raw"),
        status="failed",
        error="Failed to parse raw file",
        retryable=False,
    )
    assert _announce_result(result, locked=False) == "failed"
    assert capsys.readouterr().out.strip() == (
        "Failed QC_Metab_Neg-01.raw: Failed to parse raw file"
    )


def test_idle_message_is_once_then_hourly() -> None:
    assert _idle_message(
        announced=False, elapsed_sec=0, finished=3, skipped=3, failed=0
    ) == "Waiting for new .raw files. 3 finished, 3 skipped."
    assert (
        _idle_message(
            announced=True, elapsed_sec=3599, finished=0, skipped=0, failed=0
        )
        is None
    )
    assert (
        _idle_message(
            announced=True, elapsed_sec=3600, finished=0, skipped=0, failed=0
        )
        == "Still waiting for new .raw files."
    )
    assert (
        _idle_message(announced=False, elapsed_sec=0, finished=0, skipped=0, failed=1)
        == "Waiting for new .raw files. 1 failed."
    )


def test_watch_log_for_a_matched_file_is_one_result_line(
    monkeypatch, tmp_path, capsys
) -> None:
    config, raw_dir = _config(tmp_path)
    raw_file = raw_dir / "QC_Metab_Neg-01.raw"
    raw_file.write_bytes(b"x")

    def _ok(self, raw_file: Path, *, expected_polarity: str | None = None):
        return ProcessResult(
            raw_file=raw_file,
            status="completed",
            rows=15,
            targets=15,
            polarity="negative",
            output_csv=tmp_path / "matches.csv",
            trace_csv=tmp_path / "traces.csv",
        )

    monkeypatch.setattr(ProcessorOrchestrator, "process_single_raw", _ok)
    monkeypatch.setattr(
        "metabwatch.pipeline._run_synthesis",
        lambda *_args, **_kwargs: tmp_path / "dashboard.html",
    )

    assert run_watch_mode(config, once=True) == 0
    out = capsys.readouterr().out
    assert f"Processing {raw_dir.resolve()}." in out
    assert f"Output: {config.processor.output_dir}" in out
    assert "1 file queued" in out
    assert f"Dashboard: {config.synthesizer.html_output.resolve()}" in out
    assert "QC_Metab_Neg-01.raw" in out
    assert "  15 of 15 matched. Run locked to negative." in out
    assert "SUMMARY" not in out
    assert "[export]" not in out
    assert "[completed]" not in out
    assert "Processing raw files" not in out
    assert "\033]8;;" not in out


def test_watch_log_skips_polarity_mismatch_in_one_line(
    monkeypatch, tmp_path, capsys
) -> None:
    config, raw_dir = _config(tmp_path, polarity="negative")
    name = "QC_Metab_Pos-02.raw"
    (raw_dir / name).write_bytes(b"x")

    def _fail(self, raw_file: Path, *, expected_polarity: str | None = None):
        return ProcessResult(
            raw_file=raw_file,
            status="failed",
            error=(
                f"Polarity mismatch: file {raw_file.name} is 'positive' "
                "but this run is locked to 'negative'. "
                "MetabWatch does not allow mixed polarities in one input folder / run."
            ),
            retryable=False,
        )

    monkeypatch.setattr(ProcessorOrchestrator, "process_single_raw", _fail)
    _stop_after(monkeypatch, 2)
    assert run_watch_mode(config, once=False) == 0
    out = capsys.readouterr().out
    assert "Run locked to negative." in out
    assert (
        "Skipped QC_Metab_Pos-02.raw — positive file; this run is negative" in out
    )
    assert out.count("Skipped QC_Metab_Pos-02.raw") == 1
    assert out.count("Waiting for new .raw files. 1 skipped.") == 1
    assert "Still waiting" not in out
    assert "retryable=" not in out
    assert "does not allow mixed polarities" not in out
    assert "[failed]" not in out


def test_watch_idle_log_is_printed_once_across_polls(
    monkeypatch, tmp_path, capsys
) -> None:
    config, _raw_dir = _config(tmp_path)
    _stop_after(monkeypatch, 2)
    assert run_watch_mode(config, once=False) == 0
    out = capsys.readouterr().out
    assert out.count("Waiting for new .raw files.") == 1
    assert "Still waiting" not in out
    assert "discovery_mode" not in out
    assert "0file" not in out
    assert "No new stable" not in out
    assert "Press Ctrl+C to exit." in out


def test_watch_idle_log_repeats_after_the_interval(
    monkeypatch, tmp_path, capsys
) -> None:
    config, _raw_dir = _config(tmp_path)
    _stop_after(monkeypatch, 2)
    monkeypatch.setattr("metabwatch.pipeline._IDLE_LOG_INTERVAL_SEC", 0)
    assert run_watch_mode(config, once=False) == 0
    out = capsys.readouterr().out
    assert out.count("Waiting for new .raw files.") == 1
    assert out.count("Still waiting for new .raw files.") == 1


def test_gui_watch_startup_mentions_stop_once(monkeypatch, tmp_path, capsys) -> None:
    config, _raw_dir = _config(tmp_path)
    assert run_watch_mode(config, once=True, stop_event=threading.Event()) == 0
    out = capsys.readouterr().out
    assert "Use Stop to exit." in out
    assert out.count("Use Stop to exit.") == 1
    assert "not frozen" not in out
