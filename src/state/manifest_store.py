from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path


"""Manifest-backed persistent state store for pipeline idempotency.

This module provides `ManifestStateStore` which persists simple metadata
about processed `.raw` files (fingerprint, status, attempts, artifact paths)
to a JSON file. The store performs atomic writes and exposes helpers for
recovering stale `in_progress` entries.
"""


@dataclass
class ManifestEntry:
    """Record for a single processed raw file entry.

    Attributes
    ----------
    raw_file : str
        Absolute path string for the `.raw` file.
    fingerprint : str
        SHA256 fingerprint derived from path,size,mtime.
    size : int
        File size in bytes.
    mtime : float
        File modification timestamp.
    status : str
        Processing status: 'in_progress', 'completed', or 'failed'.
    attempts : int
        Number of processing attempts recorded.
    updated_at : str
        ISO8601 timestamp of last update.
    output_csv : str | None
        Path to produced matches CSV (when completed).
    trace_csv : str | None
        Path to MS1 trace CSV (when produced).
    error : str | None
        Truncated error message for failures.
    acquisition_time : str | None
        Sample acquisition time in UTC ISO8601 when available.
    """
    raw_file: str
    fingerprint: str
    size: int
    mtime: float
    status: str
    attempts: int
    updated_at: str
    output_csv: str | None = None
    trace_csv: str | None = None
    error: str | None = None
    acquisition_time: str | None = None


class ManifestStateStore:
    def __init__(
        self,
        manifest_json: Path,
        stale_in_progress_sec: int = 3600,
    ):
        """Create or load a manifest-backed state store.

        Parameters
        ----------
        manifest_json : Path
            Path to the manifest JSON file that will be read/written.
        stale_in_progress_sec : int
            Seconds after which an `in_progress` entry is considered stale
            and will be marked failed on recovery.
        """

        self.manifest_json = manifest_json
        self.stale_in_progress_sec = stale_in_progress_sec
        self.manifest_json.parent.mkdir(parents=True, exist_ok=True)
        self._entries: dict[str, ManifestEntry] = {}
        self._load()

    @staticmethod
    def _now_iso() -> str:
        """Return current UTC time as ISO8601 string."""
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def fingerprint(raw_file: Path) -> tuple[str, int, float]:
        """Compute a stable fingerprint tuple for a file.

        Returns
        -------
        tuple[str, int, float]
            (hex_sha256, size, mtime)
        """
        stat = raw_file.stat()
        material = f"{raw_file.resolve()}|{stat.st_size}|{stat.st_mtime}"
        return hashlib.sha256(material.encode("utf-8")).hexdigest(), stat.st_size, stat.st_mtime

    def _load(self) -> None:
        """Load manifest JSON into memory if it exists."""
        if not self.manifest_json.exists():
            return
        with self.manifest_json.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        for row in payload.get("entries", []):
            entry = ManifestEntry(**row)
            self._entries[entry.raw_file] = entry

    def _flush(self) -> None:
        """Atomically flush in-memory entries to the manifest JSON.

        Writes to a temporary file then replaces the canonical path to avoid
        partial writes.
        """
        tmp_path = self.manifest_json.with_suffix(self.manifest_json.suffix + ".tmp")
        payload = {
            "updated_at": self._now_iso(),
            "entries": [asdict(entry) for entry in self._entries.values()],
        }
        with tmp_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
        tmp_path.replace(self.manifest_json)

    def recover_stale_in_progress(self) -> None:
        """Mark entries that have been `in_progress` for too long as failed.

        This helps recover from crashes or interrupted runs by ensuring
        entries do not remain indefinitely locked in `in_progress`.
        """
        now_ts = datetime.now(timezone.utc).timestamp()
        changed = False
        for entry in self._entries.values():
            if entry.status != "in_progress":
                continue
            updated_ts = datetime.fromisoformat(entry.updated_at).timestamp()
            if now_ts - updated_ts >= self.stale_in_progress_sec:
                entry.status = "failed"
                entry.error = "Recovered stale in_progress entry"
                changed = True
        if changed:
            self._flush()

    def should_process(self, raw_file: Path) -> bool:
        """Return True when the file should be processed.

        A file should be processed when there is no manifest entry, when the
        fingerprint changed, or when the last recorded status is not
        `completed`.
        """
        key = str(raw_file.resolve())
        entry = self._entries.get(key)
        if entry is None:
            return True
        fingerprint, _, _ = self.fingerprint(raw_file)
        if entry.fingerprint != fingerprint:
            return True
        return entry.status != "completed"

    def mark_in_progress(self, raw_file: Path) -> ManifestEntry:
        """Record that processing for `raw_file` has started and persist.

        Returns the new or updated ManifestEntry.
        """
        key = str(raw_file.resolve())
        fingerprint, size, mtime = self.fingerprint(raw_file)
        previous = self._entries.get(key)
        attempts = (previous.attempts + 1) if previous else 1
        entry = ManifestEntry(
            raw_file=key,
            fingerprint=fingerprint,
            size=size,
            mtime=mtime,
            status="in_progress",
            attempts=attempts,
            updated_at=self._now_iso(),
            output_csv=previous.output_csv if previous else None,
            trace_csv=previous.trace_csv if previous else None,
            error=None,
            acquisition_time=previous.acquisition_time if previous else None,
        )
        self._entries[key] = entry
        self._flush()
        return entry

    def mark_completed(
        self,
        raw_file: Path,
        output_csv: Path,
        trace_csv: Path,
        acquisition_time: str | None = None,
    ) -> None:
        """Mark an entry completed and persist artifact paths."""
        key = str(raw_file.resolve())
        if key not in self._entries:
            self.mark_in_progress(raw_file)
        entry = self._entries[key]
        entry.status = "completed"
        entry.output_csv = str(output_csv.resolve())
        entry.trace_csv = str(trace_csv.resolve())
        entry.acquisition_time = acquisition_time
        entry.error = None
        entry.updated_at = self._now_iso()
        self._flush()

    def mark_failed(self, raw_file: Path, error: str) -> None:
        """Mark an entry as failed with an error message and persist."""
        key = str(raw_file.resolve())
        if key not in self._entries:
            self.mark_in_progress(raw_file)
        entry = self._entries[key]
        entry.status = "failed"
        entry.error = error[:1000]
        entry.updated_at = self._now_iso()
        self._flush()

    def get_attempts(self, raw_file: Path) -> int:
        """Return the number of recorded attempts for a given raw file."""
        key = str(raw_file.resolve())
        entry = self._entries.get(key)
        return entry.attempts if entry else 0

    def has_entries(self) -> bool:
        """Return True if the store contains any manifest entries."""
        return bool(self._entries)
