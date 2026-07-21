"""Unit tests for RawFileWatcher stability and candidate registration."""

from __future__ import annotations

import time
from pathlib import Path

from metabwatch.watcher.file_watcher import RawFileWatcher


def _write_raw(path: Path, content: bytes = b"data") -> Path:
    path.write_bytes(content)
    return path


def test_file_not_stable_on_first_sight(tmp_path: Path) -> None:
    raw = _write_raw(tmp_path / "sample.raw")
    watcher = RawFileWatcher(raw_dirs=(tmp_path,), stability_wait_sec=0.2)

    assert watcher.get_stable_new_files() == []
    # Still not stable immediately after first sight.
    assert watcher.get_stable_new_files() == []


def test_file_becomes_stable_after_wait(tmp_path: Path) -> None:
    raw = _write_raw(tmp_path / "sample.raw")
    watcher = RawFileWatcher(raw_dirs=(tmp_path,), stability_wait_sec=0.15)

    assert watcher.get_stable_new_files() == []
    time.sleep(0.2)
    stable = watcher.get_stable_new_files()
    assert len(stable) == 1
    assert stable[0].name == "sample.raw"
    assert stable[0] == raw.resolve()


def test_growing_file_resets_stability_timer(tmp_path: Path) -> None:
    raw = _write_raw(tmp_path / "growing.raw", b"a")
    watcher = RawFileWatcher(raw_dirs=(tmp_path,), stability_wait_sec=0.2)

    assert watcher.get_stable_new_files() == []
    time.sleep(0.12)
    raw.write_bytes(b"abcdef")  # size/mtime change
    assert watcher.get_stable_new_files() == []
    time.sleep(0.12)
    # Not enough uninterrupted stable time yet.
    assert watcher.get_stable_new_files() == []
    time.sleep(0.12)
    stable = watcher.get_stable_new_files()
    assert len(stable) == 1
    assert stable[0].name == "growing.raw"


def test_register_only_mode_without_directory_scan(tmp_path: Path) -> None:
    raw = _write_raw(tmp_path / "event.raw")
    other = _write_raw(tmp_path / "unseen.raw")
    watcher = RawFileWatcher(raw_dirs=(tmp_path,), stability_wait_sec=0.1)

    watcher.register(raw)
    assert watcher.get_stable_new_files(scan_directory=False) == []
    time.sleep(0.15)
    stable = watcher.get_stable_new_files(scan_directory=False)
    assert [p.name for p in stable] == ["event.raw"]
    # unseen.raw was never registered and scan is off.
    assert all(p.name != other.name for p in stable)


def test_list_current_raw_files_case_insensitive_suffix(tmp_path: Path) -> None:
    _write_raw(tmp_path / "a.raw")
    _write_raw(tmp_path / "b.RAW")
    _write_raw(tmp_path / "c.txt")
    watcher = RawFileWatcher(raw_dirs=(tmp_path,), stability_wait_sec=1.0)

    names = {p.name for p in watcher.list_current_raw_files()}
    assert names == {"a.raw", "b.RAW"}


def test_missing_files_pruned_from_registration(tmp_path: Path) -> None:
    raw = _write_raw(tmp_path / "gone.raw")
    watcher = RawFileWatcher(raw_dirs=(tmp_path,), stability_wait_sec=0.05)
    watcher.register(raw)
    watcher.get_stable_new_files(scan_directory=False)
    raw.unlink()
    assert watcher.get_stable_new_files(scan_directory=False) == []
    # Internal registration should no longer hold the missing path.
    assert raw.resolve() not in watcher._registered  # noqa: SLF001
