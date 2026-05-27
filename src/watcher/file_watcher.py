from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import time


@dataclass
class FileSnapshot:
    size: int
    mtime: float
    """Lightweight snapshot of file size and mtime.

    Parameters
    ----------
    size : int
        File size in bytes.
    mtime : float
        File modification timestamp.
    """


class RawFileWatcher:
    def __init__(self, raw_dirs: tuple[Path, ...], stability_wait_sec: float = 20.0):
        self.raw_dirs = raw_dirs
        self.stability_wait_sec = stability_wait_sec
        self._first_seen: dict[Path, float] = {}
        self._snapshots: dict[Path, FileSnapshot] = {}
    """Poll directories and emit paths that have become stable.

    Parameters
    ----------
    raw_dirs : tuple[Path, ...]
        Iterable of directories to scan for `*.raw` files.
    stability_wait_sec : float, optional
        Seconds a file must be unmodified to be considered stable.
    """

    def _iter_raw_candidates(self) -> list[Path]:
        candidates: list[Path] = []
        for raw_dir in self.raw_dirs:
            if not raw_dir.exists():
                continue
            for path in raw_dir.glob("*.raw"):
                if path.is_file():
                    candidates.append(path)
        return sorted(candidates)
    """Return a list of files that have been stable for the configured window.

    The function updates internal snapshots and a `first_seen` timestamp to
    ensure that files are only considered stable after being unchanged for
    `stability_wait_sec` seconds.
    """

    def list_current_raw_files(self) -> list[Path]:
        return self._iter_raw_candidates()

    def get_stable_new_files(self) -> list[Path]:
        stable: list[Path] = []
        now = time.time()
        live_paths = set()

        for path in self._iter_raw_candidates():
            live_paths.add(path)
            stat = path.stat()
            snapshot = FileSnapshot(size=stat.st_size, mtime=stat.st_mtime)
            prev = self._snapshots.get(path)
            self._snapshots[path] = snapshot

            if path not in self._first_seen:
                self._first_seen[path] = now
                continue

            if prev is None or prev.size != snapshot.size or prev.mtime != snapshot.mtime:
                self._first_seen[path] = now
                continue

            age = now - self._first_seen[path]
            if age >= self.stability_wait_sec:
                stable.append(path)

        missing = [p for p in self._snapshots if p not in live_paths]
        for path in missing:
            self._snapshots.pop(path, None)
            self._first_seen.pop(path, None)

        return stable
