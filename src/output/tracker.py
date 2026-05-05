from __future__ import annotations

import time


class OutputTracker:
    def __init__(self, debounce_sec: float = 5.0):
        self.debounce_sec = debounce_sec
        self._last_event_ts: float | None = None
        self._dirty = False

    def register_new_output(self) -> None:
        self._last_event_ts = time.time()
        self._dirty = True

    def synthesis_due(self) -> bool:
        if not self._dirty or self._last_event_ts is None:
            return False
        return (time.time() - self._last_event_ts) >= self.debounce_sec

    def clear(self) -> None:
        self._dirty = False
        self._last_event_ts = None
