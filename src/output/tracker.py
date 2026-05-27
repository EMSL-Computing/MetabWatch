from __future__ import annotations

import time


class OutputTracker:
    """Simple debounce tracker for output events.

    The tracker records the timestamp of the most recent output event and
    reports when sufficient time has elapsed (debounce window) to trigger a
    synthesis update.
    """

    def __init__(self, debounce_sec: float = 5.0):
        """Create a tracker with a debounce window in seconds.

        Parameters
        ----------
        debounce_sec : float
            Seconds to wait after the last event before synthesis is due.
        """
        self.debounce_sec = debounce_sec
        self._last_event_ts: float | None = None
        self._dirty = False

    def register_new_output(self) -> None:
        """Record that a new output artifact was written now."""
        self._last_event_ts = time.time()
        self._dirty = True

    def synthesis_due(self) -> bool:
        """Return True when enough time has passed since last output.

        Returns
        -------
        bool
            True if the debounce window elapsed and synthesis should run.
        """
        if not self._dirty or self._last_event_ts is None:
            return False
        return (time.time() - self._last_event_ts) >= self.debounce_sec

    def clear(self) -> None:
        """Clear the pending-output state after synthesis completes."""
        self._dirty = False
        self._last_event_ts = None
