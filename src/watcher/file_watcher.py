from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import time
from typing import Iterable


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


def _is_raw_file(path: Path) -> bool:
    """Return True when path looks like a Thermo ``.raw`` file (case-insensitive)."""
    return path.suffix.lower() == ".raw"


class RawFileWatcher:
    """Track ``.raw`` candidates and emit paths that have become stable.

    Discovery (directory scan or filesystem events) feeds candidates via
    :meth:`register` / full scans. Stability uses size/mtime snapshots so
    Thermo creation events that fire before the write finishes are not
    processed too early.

    Parameters
    ----------
    raw_dirs : tuple[Path, ...]
        Iterable of directories to scan for ``*.raw`` files.
    stability_wait_sec : float, optional
        Seconds a file must be unmodified to be considered stable.
    """

    def __init__(self, raw_dirs: tuple[Path, ...], stability_wait_sec: float = 20.0):
        self.raw_dirs = raw_dirs
        self.stability_wait_sec = stability_wait_sec
        self._first_seen: dict[Path, float] = {}
        self._snapshots: dict[Path, FileSnapshot] = {}
        self._registered: set[Path] = set()

    def _normalize(self, path: Path) -> Path:
        try:
            return path.resolve()
        except OSError:
            return path.absolute()

    def register(self, path: Path) -> None:
        """Register a candidate path for stability tracking."""
        if not _is_raw_file(path):
            return
        self._registered.add(self._normalize(path))

    def register_many(self, paths: Iterable[Path]) -> None:
        """Register multiple candidate paths."""
        for path in paths:
            self.register(path)

    def _iter_raw_candidates(self) -> list[Path]:
        candidates: list[Path] = []
        for raw_dir in self.raw_dirs:
            if not raw_dir.exists():
                continue
            for path in raw_dir.iterdir():
                if path.is_file() and _is_raw_file(path):
                    candidates.append(self._normalize(path))
        return sorted(candidates)

    def list_current_raw_files(self) -> list[Path]:
        """Return a sorted list of ``.raw`` files currently on disk."""
        return self._iter_raw_candidates()

    def get_stable_new_files(self, *, scan_directory: bool = True) -> list[Path]:
        """Return files that have been stable for the configured window.

        Parameters
        ----------
        scan_directory : bool
            When True (default), re-scan watched directories and union results
            with registered candidates. When False, only evaluate paths already
            registered via :meth:`register` (or prior scans).
        """
        if scan_directory:
            scanned = self._iter_raw_candidates()
            self.register_many(scanned)
            paths = sorted(self._registered)
        else:
            paths = sorted(self._registered)

        return self._evaluate_stability(paths)

    def _evaluate_stability(self, paths: Iterable[Path]) -> list[Path]:
        """Update snapshots and return paths stable for ``stability_wait_sec``."""
        stable: list[Path] = []
        now = time.time()
        live_paths: set[Path] = set()

        for path in paths:
            path = self._normalize(path)
            if not path.exists() or not path.is_file():
                continue
            if not _is_raw_file(path):
                continue

            live_paths.add(path)
            try:
                stat = path.stat()
            except OSError:
                continue

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

        # Prune missing paths from internal state and registration set.
        tracked = set(self._snapshots) | set(self._first_seen) | set(self._registered)
        missing = [p for p in tracked if p not in live_paths]
        for path in missing:
            # Keep registered-but-not-yet-visible paths only if still registered
            # and we did not just fail a live existence check for a registered
            # path that was in the evaluation set — always drop gone files.
            if path not in live_paths:
                self._snapshots.pop(path, None)
                self._first_seen.pop(path, None)
                # Drop from registered only when the file is gone from disk.
                if not path.exists():
                    self._registered.discard(path)

        return stable
