from __future__ import annotations

"""Filesystem notifications for new Thermo ``.raw`` files.

Pattern inspired by CoreMS-AutoUpload's watchdog Observer + event handler
flow: create/move events register candidates; completeness remains the
caller's size/mtime stability check.
"""

import threading
from pathlib import Path

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer


def _is_raw_path(path_str: str) -> bool:
    return Path(path_str).suffix.lower() == ".raw"


class RawFileEventHandler(FileSystemEventHandler):
    """Collect create/move events for ``.raw`` files into a thread-safe set."""

    def __init__(self) -> None:
        super().__init__()
        self._lock = threading.Lock()
        self._pending: set[Path] = set()
        self.event = threading.Event()

    def _accept(self, path_str: str, is_directory: bool) -> None:
        if is_directory or not _is_raw_path(path_str):
            return
        path = Path(path_str)
        try:
            path = path.resolve()
        except OSError:
            path = path.absolute()
        with self._lock:
            self._pending.add(path)
        self.event.set()

    def on_created(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        self._accept(event.src_path, is_directory=False)

    def on_moved(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        dest = getattr(event, "dest_path", None)
        if dest:
            self._accept(dest, is_directory=False)

    def drain(self) -> list[Path]:
        """Return and clear pending paths (main-thread safe)."""
        with self._lock:
            paths = sorted(self._pending)
            self._pending.clear()
        self.event.clear()
        return paths


class RawDirectoryObserver:
    """Thin wrapper around ``watchdog.observers.Observer`` for one directory.

    Parameters
    ----------
    recursive : bool
        Watch subdirectories. Default False to match top-level-only scanning.
    """

    def __init__(self, *, recursive: bool = False) -> None:
        self.recursive = recursive
        self._handler = RawFileEventHandler()
        self._observer: Observer | None = None
        self._watch_path: Path | None = None

    @property
    def event(self) -> threading.Event:
        """Event set when a new candidate arrives (for optional wait/wake)."""
        return self._handler.event

    def start(self, path: Path) -> None:
        """Schedule and start watching ``path``. No-op if already started."""
        if self._observer is not None:
            return
        watch_path = Path(path)
        watch_path.mkdir(parents=True, exist_ok=True)
        observer = Observer()
        observer.schedule(self._handler, str(watch_path), recursive=self.recursive)
        observer.start()
        self._observer = observer
        self._watch_path = watch_path

    def stop(self, *, timeout: float = 5.0) -> None:
        """Stop the observer if running."""
        observer = self._observer
        if observer is None:
            return
        observer.stop()
        observer.join(timeout=timeout)
        self._observer = None

    def drain(self) -> list[Path]:
        """Drain pending ``.raw`` paths discovered via FS events."""
        return self._handler.drain()
