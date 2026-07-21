"""Unit tests for watchdog event handler filtering."""

from __future__ import annotations

from pathlib import Path

from watchdog.events import (
    DirCreatedEvent,
    FileCreatedEvent,
    FileMovedEvent,
    FileModifiedEvent,
)

from metabwatch.watcher.fs_observer import RawDirectoryObserver, RawFileEventHandler


def test_handler_accepts_raw_create_events(tmp_path: Path) -> None:
    handler = RawFileEventHandler()
    raw = tmp_path / "sample.raw"
    raw.write_bytes(b"x")

    handler.on_created(FileCreatedEvent(str(raw)))
    pending = handler.drain()
    assert len(pending) == 1
    assert pending[0] == raw.resolve()
    # Drain clears.
    assert handler.drain() == []


def test_handler_accepts_raw_move_dest(tmp_path: Path) -> None:
    handler = RawFileEventHandler()
    src = tmp_path / "tmp.bin"
    dest = tmp_path / "final.raw"
    dest.write_bytes(b"x")

    handler.on_moved(FileMovedEvent(str(src), str(dest)))
    pending = handler.drain()
    assert [p.name for p in pending] == ["final.raw"]


def test_handler_ignores_non_raw_and_directories(tmp_path: Path) -> None:
    handler = RawFileEventHandler()
    txt = tmp_path / "notes.txt"
    txt.write_text("hi", encoding="utf-8")
    sub = tmp_path / "subdir.raw"
    sub.mkdir()

    handler.on_created(FileCreatedEvent(str(txt)))
    handler.on_created(DirCreatedEvent(str(sub)))
    handler.on_modified(FileModifiedEvent(str(tmp_path / "sample.raw")))
    assert handler.drain() == []


def test_handler_accepts_uppercase_raw_suffix(tmp_path: Path) -> None:
    handler = RawFileEventHandler()
    raw = tmp_path / "SAMPLE.RAW"
    raw.write_bytes(b"x")
    handler.on_created(FileCreatedEvent(str(raw)))
    assert [p.name for p in handler.drain()] == ["SAMPLE.RAW"]


def test_observer_start_stop_and_drain_empty(tmp_path: Path) -> None:
    observer = RawDirectoryObserver(recursive=False)
    observer.start(tmp_path)
    try:
        assert observer.drain() == []
        # Second start is a no-op.
        observer.start(tmp_path)
    finally:
        observer.stop()
        observer.stop()  # safe when not started
