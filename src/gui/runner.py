"""Background pipeline runner for the MetabWatch GUI."""

from __future__ import annotations

import queue
import sys
import threading
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, TextIO

from metabwatch.config import PipelineConfig
from metabwatch.gui.validation import GuiRunRequest, resolve_config
from metabwatch.pipeline import run_watch_mode


class _QueueWriter:
    """File-like object that pushes written text into a queue as lines."""

    def __init__(self, log_queue: queue.Queue[str]) -> None:
        self._queue = log_queue
        self._buffer = ""

    def write(self, data: str) -> int:
        if not data:
            return 0
        self._buffer += data
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            self._queue.put(line)
        return len(data)

    def flush(self) -> None:
        if self._buffer:
            self._queue.put(self._buffer)
            self._buffer = ""

    def isatty(self) -> bool:
        return False


@dataclass
class RunnerState:
    """Snapshot of the last completed (or active) run for UI helpers."""

    config: PipelineConfig | None = None
    exit_code: int | None = None
    error: str | None = None


class PipelineRunner:
    """Run ``run_watch_mode`` on a worker thread with cooperative stop."""

    def __init__(self) -> None:
        self.log_queue: queue.Queue[str] = queue.Queue()
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self.state = RunnerState()
        self._on_finished: Callable[[RunnerState], None] | None = None

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(
        self,
        request: GuiRunRequest,
        *,
        on_finished: Callable[[RunnerState], None] | None = None,
    ) -> None:
        """Resolve config and start the pipeline in a daemon thread.

        Raises
        ------
        RuntimeError
            If a run is already in progress.
        ValueError
            If the request is invalid or config cannot be resolved.
        """
        if self.is_running:
            raise RuntimeError("A pipeline run is already in progress.")

        config = resolve_config(request)
        self._stop_event.clear()
        self._on_finished = on_finished
        with self._lock:
            self.state = RunnerState(config=config)

        self._thread = threading.Thread(
            target=self._run,
            args=(config, request.once, request.force_reprocess),
            name="metabwatch-gui-runner",
            daemon=True,
        )
        self._thread.start()

    def request_stop(self) -> None:
        """Ask the watch loop to exit after the current file/cycle."""
        self._stop_event.set()
        self.log_queue.put("[gui] Stop requested (finishes current file, then exits)…")

    def _run(
        self,
        config: PipelineConfig,
        once: bool,
        force_reprocess: bool,
    ) -> None:
        # Belt-and-suspenders: keep plots off GUI backends on the worker thread.
        try:
            import matplotlib

            matplotlib.use("Agg", force=True)
        except Exception:
            pass

        writer = _QueueWriter(self.log_queue)
        old_stdout: TextIO = sys.stdout
        old_stderr: TextIO = sys.stderr
        exit_code = 1
        error: str | None = None
        try:
            sys.stdout = writer  # type: ignore[assignment]
            sys.stderr = writer  # type: ignore[assignment]
            mode_label = "once" if once else "watch"
            self.log_queue.put(
                f"[gui] Starting pipeline ({mode_label}"
                f"{', force-reprocess' if force_reprocess else ''})…"
            )
            self.log_queue.put(f"[gui] Input:  {config.watcher.raw_dir}")
            self.log_queue.put(f"[gui] Output: {config.processor.output_dir}")
            if not once:
                self.log_queue.put(
                    "[gui] Watch mode: after the current files finish, the app "
                    "stays idle until new .raw files appear (not frozen)."
                )
            exit_code = run_watch_mode(
                config=config,
                once=once,
                force_reprocess=force_reprocess,
                stop_event=self._stop_event,
            )
            if self._stop_event.is_set() and exit_code == 0:
                self.log_queue.put("[gui] Pipeline stopped.")
            else:
                self.log_queue.put(f"[gui] Pipeline finished with exit code {exit_code}.")
        except Exception as exc:  # pragma: no cover - surfaced to log + state
            error = str(exc)
            self.log_queue.put(f"[gui] Error: {exc}")
            self.log_queue.put(traceback.format_exc())
            exit_code = 1
        finally:
            writer.flush()
            sys.stdout = old_stdout
            sys.stderr = old_stderr
            with self._lock:
                self.state = RunnerState(
                    config=config,
                    exit_code=exit_code,
                    error=error,
                )
                finished_state = self.state
            callback = self._on_finished
            if callback is not None:
                try:
                    callback(finished_state)
                except Exception:
                    pass

    def dashboard_path(self) -> Path | None:
        """Return the dashboard HTML path from the last/current config."""
        with self._lock:
            if self.state.config is None:
                return None
            return self.state.config.synthesizer.html_output

    def output_dir(self) -> Path | None:
        """Return the output directory from the last/current config."""
        with self._lock:
            if self.state.config is None:
                return None
            return self.state.config.processor.output_dir
