from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class ManifestEntry:
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


class ManifestStateStore:
    def __init__(
        self,
        manifest_json: Path,
        manifest_csv: Path | None = None,
        stale_in_progress_sec: int = 3600,
    ):
        self.manifest_json = manifest_json
        self.manifest_csv = manifest_csv
        self.stale_in_progress_sec = stale_in_progress_sec
        self.manifest_json.parent.mkdir(parents=True, exist_ok=True)
        self._entries: dict[str, ManifestEntry] = {}
        self._load()

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def fingerprint(raw_file: Path) -> tuple[str, int, float]:
        stat = raw_file.stat()
        material = f"{raw_file.resolve()}|{stat.st_size}|{stat.st_mtime}"
        return hashlib.sha256(material.encode("utf-8")).hexdigest(), stat.st_size, stat.st_mtime

    def _load(self) -> None:
        if not self.manifest_json.exists():
            return
        with self.manifest_json.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        for row in payload.get("entries", []):
            entry = ManifestEntry(**row)
            self._entries[entry.raw_file] = entry

    def _flush(self) -> None:
        tmp_path = self.manifest_json.with_suffix(self.manifest_json.suffix + ".tmp")
        payload = {
            "updated_at": self._now_iso(),
            "entries": [asdict(entry) for entry in self._entries.values()],
        }
        with tmp_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
        tmp_path.replace(self.manifest_json)

        if self.manifest_csv:
            self.manifest_csv.parent.mkdir(parents=True, exist_ok=True)
            with self.manifest_csv.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(ManifestEntry.__dataclass_fields__))
                writer.writeheader()
                for entry in self._entries.values():
                    writer.writerow(asdict(entry))

    def recover_stale_in_progress(self) -> None:
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
        key = str(raw_file.resolve())
        entry = self._entries.get(key)
        if entry is None:
            return True
        fingerprint, _, _ = self.fingerprint(raw_file)
        if entry.fingerprint != fingerprint:
            return True
        return entry.status != "completed"

    def mark_in_progress(self, raw_file: Path) -> ManifestEntry:
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
        )
        self._entries[key] = entry
        self._flush()
        return entry

    def mark_completed(self, raw_file: Path, output_csv: Path, trace_csv: Path) -> None:
        key = str(raw_file.resolve())
        if key not in self._entries:
            self.mark_in_progress(raw_file)
        entry = self._entries[key]
        entry.status = "completed"
        entry.output_csv = str(output_csv.resolve())
        entry.trace_csv = str(trace_csv.resolve())
        entry.error = None
        entry.updated_at = self._now_iso()
        self._flush()

    def mark_failed(self, raw_file: Path, error: str) -> None:
        key = str(raw_file.resolve())
        if key not in self._entries:
            self.mark_in_progress(raw_file)
        entry = self._entries[key]
        entry.status = "failed"
        entry.error = error[:1000]
        entry.updated_at = self._now_iso()
        self._flush()

    def get_attempts(self, raw_file: Path) -> int:
        key = str(raw_file.resolve())
        entry = self._entries.get(key)
        return entry.attempts if entry else 0
