from __future__ import annotations

"""Simple in-memory FIFO processing queue with deduplication."""

from collections import deque
from pathlib import Path


class ProcessingQueue:
    """A small FIFO queue that prevents duplicate enqueues.

    Methods
    -------
    enqueue(raw_file)
        Add `raw_file` to the queue if not already present. Returns True if
        enqueued, False if it was already present.
    dequeue()
        Pop and return the next `Path` or `None` if empty.
    has_pending()
        Return True when the queue contains items.
    """

    def __init__(self):
        self._queue: deque[Path] = deque()
        self._enqueued: set[Path] = set()

    def enqueue(self, raw_file: Path) -> bool:
        """Enqueue a `raw_file` if not already present.

        Parameters
        ----------
        raw_file : Path
            Path to a `.raw` file to enqueue.

        Returns
        -------
        bool
            True if the file was added, False if it was already queued.
        """
        if raw_file in self._enqueued:
            return False
        self._queue.append(raw_file)
        self._enqueued.add(raw_file)
        return True

    def dequeue(self) -> Path | None:
        """Pop the next enqueued Path or return None if empty."""
        if not self._queue:
            return None
        raw_file = self._queue.popleft()
        self._enqueued.discard(raw_file)
        return raw_file

    def has_pending(self) -> bool:
        """Return True if there are pending items in the queue."""
        return bool(self._queue)
