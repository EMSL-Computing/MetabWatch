from __future__ import annotations

from collections import deque
from pathlib import Path


class ProcessingQueue:
    def __init__(self):
        self._queue: deque[Path] = deque()
        self._enqueued: set[Path] = set()

    def enqueue(self, raw_file: Path) -> bool:
        if raw_file in self._enqueued:
            return False
        self._queue.append(raw_file)
        self._enqueued.add(raw_file)
        return True

    def dequeue(self) -> Path | None:
        if not self._queue:
            return None
        raw_file = self._queue.popleft()
        self._enqueued.discard(raw_file)
        return raw_file

    def has_pending(self) -> bool:
        return bool(self._queue)
