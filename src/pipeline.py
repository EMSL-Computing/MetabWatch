from __future__ import annotations

import argparse
import re
import sys
import threading
import time
from pathlib import Path
from urllib.parse import quote

# Must run before any CoreMS / pythonnet import (processor → targeted_search).
from metabwatch.corems_runtime import ensure_dotnet_runtime

ensure_dotnet_runtime()

from metabwatch.config import PipelineConfig, load_pipeline_config
from metabwatch.output import OutputTracker
from metabwatch.pipeline_queue import ProcessingQueue, is_polarity_mismatch_error
from metabwatch.presets import METHOD_KEYS, PRESET_SPECS, build_pipeline_config
from metabwatch.processor import (
    ProcessResult,
    ProcessorOrchestrator,
    RetryPolicy,
    build_untargeted_search_space,
)
from metabwatch.state import ManifestStateStore
from metabwatch.synthesis import HTMLSynthesizer
from metabwatch.watcher import RawDirectoryObserver, RawFileWatcher

try:
    from tqdm import tqdm
except ImportError:  # pragma: no cover
    def tqdm(iterable, **_: object):
        return iterable


def _build_runtime(config: PipelineConfig):
    """Build runtime components from a PipelineConfig.

    Parameters
    ----------
    config : PipelineConfig
        Resolved pipeline configuration.

    Returns
    -------
    tuple
        (orchestrator, retry_policy, watcher, queue, state_store,
        output_tracker, synthesizer)
    """

    orchestrator = ProcessorOrchestrator(
        standards_csv=config.search_space.csv_path,
        params_path=config.processor.params_path,
        output_dir=config.processor.output_dir,
        mz_tolerance_ppm=config.processor.mz_tolerance_ppm,
        rt_tolerance=config.processor.rt_tolerance,
        min_area=config.processor.min_area,
        plot_eics=config.processor.plot_eics,
        plot_tic=config.processor.plot_tic,
        integrate_mass_features=config.processor.integrate_mass_features,
        cluster_mass_features=config.processor.cluster_mass_features,
    )
    retry_policy = RetryPolicy(
        max_retries=config.max_retries,
        initial_backoff_sec=config.initial_backoff_sec,
        backoff_multiplier=config.backoff_multiplier,
    )
    watcher = RawFileWatcher(
        raw_dirs=(config.watcher.raw_dir,),
        stability_wait_sec=config.watcher.stability_wait_sec,
    )
    queue = ProcessingQueue()
    state_store = ManifestStateStore(
        manifest_json=config.state.pipeline_manifest,
        stale_in_progress_sec=config.state.stale_in_progress_sec,
    )
    output_tracker = OutputTracker(debounce_sec=config.synthesizer.debounce_sec)
    synthesizer = HTMLSynthesizer(
        output_dirs=(config.synthesizer.output_dir,),
        html_output=config.synthesizer.html_output,
        mz_tolerance_ppm=config.synthesizer.mz_tolerance_ppm,
        rt_tolerance=config.synthesizer.rt_tolerance,
        untargeted_mode=(config.search_space.mode == "untargeted"),
    )
    return (
        orchestrator,
        retry_policy,
        watcher,
        queue,
        state_store,
        output_tracker,
        synthesizer,
    )


def _compile_sample_regex(pattern_text: str | None) -> re.Pattern[str] | None:
    """Compile optional filename-stem regex for sample gating."""
    if not pattern_text:
        return None
    return re.compile(pattern_text)


def _sample_ignore_reason(
    raw_file: Path,
    sample_regex: re.Pattern[str] | None,
    project_id: str = "",
) -> str | None:
    """Return why a sample is ignored, or None when both filters pass.

    The preset/config regex (``QC_Metab_`` / ``Pool``) is always applied when
    set. A non-empty ``project_id`` is an extra case-insensitive substring
    on the filename stem; both must pass.
    """
    if sample_regex is not None and not sample_regex.search(raw_file.stem):
        return "sample_name_regex no match"
    needle = (project_id or "").strip()
    if needle and needle.lower() not in raw_file.stem.lower():
        return "project_id no match"
    return None


def _sample_allowed(
    raw_file: Path,
    sample_regex: re.Pattern[str] | None,
    project_id: str = "",
) -> bool:
    """Return True when a sample passes regex and optional project-id filters."""
    return _sample_ignore_reason(raw_file, sample_regex, project_id) is None


# How often an idle watch run may repeat "still waiting" in the log.
_IDLE_LOG_INTERVAL_SEC = 3600.0


def _clickable_path(path: Path) -> str:
    """Return a path, wrapped as an OSC-8 link when stdout is a terminal.

    The GUI log is not a terminal. Escape sequences would show up as garbage
    there, so a plain path is used unless ``sys.stdout`` reports a TTY.
    """

    abs_path = path.resolve()
    label = str(abs_path)
    if not sys.stdout.isatty():
        return label
    uri = f"file://{quote(str(abs_path))}"
    return f"\033]8;;{uri}\033\\{label}\033]8;;\033\\"


def _files_queued_line(count: int, *, force: bool) -> str:
    noun = "file" if count == 1 else "files"
    line = f"{count} {noun} queued"
    if force:
        line += " (force reprocess)"
    return line


def _ignored_line(name: str, reason: str) -> str:
    if reason == "project_id no match":
        return f"Ignored {name}: name does not contain the project ID"
    return f"Ignored {name}: name does not match the sample filter"


def _same_run_skip_line(name: str, other_name: str) -> str:
    return f"Skipped {name}: same run as {other_name}"


def _note_same_run_skip(raw_file: Path, other: Path, announced: set[str]) -> None:
    """Print a same-run skip once per path for this process."""
    key = str(raw_file.resolve())
    if key in announced:
        return
    announced.add(key)
    print(_same_run_skip_line(raw_file.name, other.name))


def _unprefixed_twin_present(raw_file: Path, present: set[Path]) -> Path | None:
    """Return the on-disk name without a leading ``x_`` when it is the same size.

    Only the spelling that starts with ``x_`` is dropped, and only when that
    other file is in ``present``. A different size is a different file.
    """
    if not raw_file.name.startswith("x_"):
        return None
    other = ManifestStateStore.other_spelling(raw_file)
    if other is None:
        return None
    other_key = other.resolve()
    if other_key not in present:
        return None
    try:
        if raw_file.stat().st_size != other_key.stat().st_size:
            return None
    except OSError:
        return None
    return other_key


def _sample_result_line(result: ProcessResult, *, locked: bool) -> str:
    if result.targets is not None:
        body = f"{result.rows} of {result.targets} matched"
    else:
        body = f"{result.rows} matched"
    if locked and result.polarity:
        return f"  {body}. Run locked to {result.polarity}."
    return f"  {body}"


def _polarity_skip_line(name: str, error: str | None) -> str:
    actual = expected = None
    if error:
        match = re.search(
            r"is '([^']+)' but this run is locked to '([^']+)'",
            error,
        )
        if match:
            actual, expected = match.group(1), match.group(2)
    if actual and expected:
        return f"Skipped {name} — {actual} file; this run is {expected}"
    return f"Skipped {name} — polarity does not match this run"


def _announce_result(result: ProcessResult, *, locked: bool) -> str:
    """Print one outcome line. Return ``finished``, ``skipped``, or ``failed``."""
    name = result.raw_file.name
    if result.status == "completed":
        print(_sample_result_line(result, locked=locked))
        return "finished"
    if is_polarity_mismatch_error(result.error):
        print(_polarity_skip_line(name, result.error))
        return "skipped"
    print(f"Failed {name}: {result.error or 'unknown error'}")
    return "failed"


def _idle_message(
    *,
    announced: bool,
    elapsed_sec: float,
    finished: int,
    skipped: int,
    failed: int,
    interval_sec: float | None = None,
) -> str | None:
    """Return the idle log line, or None when the run should stay quiet."""
    if interval_sec is None:
        interval_sec = _IDLE_LOG_INTERVAL_SEC
    if not announced:
        counts: list[str] = []
        if finished:
            counts.append(f"{finished} finished")
        if skipped:
            counts.append(f"{skipped} skipped")
        if failed:
            counts.append(f"{failed} failed")
        if counts:
            return f"Waiting for new .raw files. {', '.join(counts)}."
        return "Waiting for new .raw files."
    if elapsed_sec >= interval_sec:
        return "Still waiting for new .raw files."
    return None


def apply_configured_polarity(
    config: PipelineConfig, state_store: ManifestStateStore
) -> str | None:
    """Lock the run polarity from config when the operator specified one.

    Returns the locked polarity, or ``None`` when config leaves polarity unset
    (first successful sample still locks the run). Raises ``ValueError`` if
    the output folder is already locked to a different polarity.
    """
    requested = config.polarity
    if requested is None:
        return None
    try:
        return state_store.set_run_polarity(requested)
    except ValueError:
        existing = state_store.get_run_polarity()
        raise ValueError(
            f"Polarity mismatch: config requests '{requested}' but this run is "
            f"locked to '{existing}' in {state_store.manifest_json.name}. "
            "MetabWatch does not allow mixed polarities in one input folder / run."
        ) from None


def _ensure_untargeted_search_space(
    config: PipelineConfig,
    raw_file: Path,
    *,
    expected_polarity: str | None = None,
) -> str | None:
    """Build the untargeted search-space CSV from `raw_file` if missing.

    Idempotent — returns immediately when the CSV already exists. No-op when
    `config.search_space.mode != 'untargeted'`. Raises on failure; the caller
    is responsible for marking the sample failed in the manifest.

    Parameters
    ----------
    config : PipelineConfig
        Resolved pipeline configuration.
    raw_file : Path
        Sample to use as the untargeted source.
    expected_polarity : str | None
        When set (from the pipeline manifest), bootstrap polarity must match.

    Returns
    -------
    str | None
        Normalized polarity when this call built the search space; otherwise
        ``None`` (mode not untargeted, CSV already present, etc.).
    """
    if config.search_space.mode != "untargeted":
        return None
    if config.search_space.csv_path.exists():
        return None

    print(
        f"[untargeted] building search space from {raw_file.name} "
        f"(top_n={config.search_space.top_n})"
    )
    diagnostic_df = build_untargeted_search_space(
        raw_file=raw_file,
        params_path=config.processor.params_path,
        output_csv=config.search_space.csv_path,
        top_n=config.search_space.top_n,
        mz_tolerance_ppm=config.processor.mz_tolerance_ppm,
        expected_polarity=expected_polarity,
    )
    polarity = diagnostic_df.attrs.get("polarity")
    if polarity is None:
        return None
    return str(polarity).strip().lower()


def _run_synthesis(
    synthesizer: HTMLSynthesizer,
    output_tracker: OutputTracker,
) -> Path:
    """Rebuild dashboard HTML and wide pivot CSV exports, then clear the tracker.

    Parameters
    ----------
    synthesizer : HTMLSynthesizer
        Dashboard/export renderer.
    output_tracker : OutputTracker
        Debounce tracker to clear after a successful rebuild.

    Returns
    -------
    Path
        Path to the generated landing dashboard HTML.
    """
    html_path = synthesizer.render()
    output_tracker.clear()
    return html_path


def _process_one(
    raw_file: Path,
    orchestrator: ProcessorOrchestrator,
    retry_policy: RetryPolicy,
    state_store: ManifestStateStore,
    output_tracker: OutputTracker,
) -> ProcessResult:
    """Process a single raw file with retry/backoff and manifest updates.

    This function marks the file as `in_progress`, invokes the processor,
    updates the manifest to `completed` or `failed`, and applies retry logic
    based on the provided `RetryPolicy`. Run polarity is read from and written
    to ``state_store`` (pipeline manifest).

    Parameters
    ----------
    raw_file : Path
        Path to the `.raw` file to process.
    orchestrator : ProcessorOrchestrator
        The processing wrapper to execute the sample run.
    retry_policy : RetryPolicy
        Retry/backoff configuration.
    state_store : ManifestStateStore
        Manifest state persistence instance.
    output_tracker : OutputTracker
        Tracker used to debounce synthesis triggers.

    Returns
    -------
    ProcessResult
        Result object describing success/failure and artifact paths.
    """

    backoff = retry_policy.initial_backoff_sec

    while True:
        state_store.mark_in_progress(raw_file)
        attempts = state_store.get_attempts(raw_file)
        expected_polarity = state_store.get_run_polarity()
        result = orchestrator.process_single_raw(
            raw_file,
            expected_polarity=expected_polarity,
        )
        if result.status == "completed":
            state_store.mark_completed(
                raw_file=raw_file,
                output_csv=result.output_csv,
                trace_csv=result.trace_csv,
                acquisition_time=result.acquisition_time,
                polarity=result.polarity,
            )
            output_tracker.register_new_output()
            return result

        state_store.mark_failed(raw_file, result.error or "unknown error")
        can_retry = result.retryable and attempts <= retry_policy.max_retries
        if can_retry:
            print(
                f"Failed {raw_file.name} (attempt {attempts}, will retry): "
                f"{result.error or 'unknown error'}"
            )
        if not can_retry:
            return result

        time.sleep(backoff)
        backoff = backoff * retry_policy.backoff_multiplier


def _wait_for_poll(
    poll_interval_sec: float,
    stop_event: threading.Event | None,
) -> bool:
    """Sleep for the poll interval, or until stop is requested.

    Returns
    -------
    bool
        True when a stop was requested; False when the full wait completed.
    """
    if stop_event is None:
        time.sleep(poll_interval_sec)
        return False
    return stop_event.wait(timeout=poll_interval_sec)


def run_watch_mode(
    config: PipelineConfig,
    once: bool = False,
    force_reprocess: bool = False,
    stop_event: threading.Event | None = None,
) -> int:
    """Run the watch loop: discover, enqueue, process, and synthesize.

    Parameters
    ----------
    config : PipelineConfig
        Resolved pipeline configuration.
    once : bool, optional
        If True, performs a single iteration and exits.
    force_reprocess : bool, optional
        If True, reprocess files even when the manifest marks them completed.
    stop_event : threading.Event | None, optional
        When set, exit the watch loop after the current cycle (cooperative
        stop for GUI). ``None`` keeps CLI behavior (Ctrl+C only).

    Returns
    -------
    int
        Exit code (0 for success, >0 for errors).
    """

    (
        orchestrator,
        retry_policy,
        watcher,
        queue,
        state_store,
        output_tracker,
        synthesizer,
    ) = _build_runtime(config)
    try:
        sample_regex = _compile_sample_regex(config.watcher.sample_name_regex)
    except re.error as exc:
        print(f"Invalid watcher.sample_name_regex: {exc}")
        return 2

    try:
        configured_polarity = apply_configured_polarity(config, state_store)
    except ValueError as exc:
        print(exc)
        return 2

    # Openable waiting page while the first sample is still processing.
    synthesizer.write_placeholder_if_missing()

    discovery_mode = config.watcher.discovery_mode
    # --once uses a full scan only (deterministic smoke tests; no observer).
    use_observer = (not once) and discovery_mode in {"hybrid", "watchdog"}
    # Full directory scan each cycle for poll/hybrid; pure watchdog relies on
    # registered candidates after the startup reconcile below.
    scan_each_cycle = once or discovery_mode in {"poll", "hybrid"}

    observer: RawDirectoryObserver | None = None
    if use_observer:
        observer = RawDirectoryObserver(recursive=False)
        observer.start(config.watcher.raw_dir)

    try:
        stop_hint = (
            "Use Stop to exit."
            if stop_event is not None
            else "Press Ctrl+C to exit."
        )
        action = "Processing" if once else "Watching"
        print(f"{action} {config.watcher.raw_dir}. {stop_hint}")
        print(f"Output: {config.processor.output_dir}")
        if configured_polarity:
            print(f"Run locked to {configured_polarity}.")
        elif state_store.get_run_polarity():
            print(f"Run locked to {state_store.get_run_polarity()}.")
        if config.watcher.project_id:
            print(
                "Only files whose name contains "
                f"{config.watcher.project_id!r}."
            )
        print(f"Dashboard: {_clickable_path(config.synthesizer.html_output)}")

        forced_enqueued: set[Path] = set()
        announced_same_run: set[str] = set()

        # Startup reconciliation: files written while MetabWatch was offline.
        reconcile_files = watcher.list_current_raw_files()
        watcher.register_many(reconcile_files)
        present = {path.resolve() for path in reconcile_files}

        if force_reprocess or not state_store.has_entries():
            bootstrap_files = reconcile_files
            enqueued = 0
            for raw_file in bootstrap_files:
                reason = _sample_ignore_reason(
                    raw_file, sample_regex, config.watcher.project_id
                )
                if reason:
                    print(_ignored_line(raw_file.name, reason))
                    continue
                twin = _unprefixed_twin_present(raw_file, present)
                if twin is not None:
                    _note_same_run_skip(raw_file, twin, announced_same_run)
                    continue
                if force_reprocess or state_store.should_process(raw_file):
                    queue.enqueue(raw_file)
                    forced_enqueued.add(raw_file)
                    enqueued += 1
            if enqueued:
                print(_files_queued_line(enqueued, force=force_reprocess))

        state_store.recover_stale_in_progress()

        idle_announced = False
        last_idle_log = 0.0

        while True:
            if stop_event is not None and stop_event.is_set():
                print("Stop requested.")
                return 0

            if observer is not None:
                watcher.register_many(observer.drain())

            stable_files = watcher.get_stable_new_files(
                scan_directory=scan_each_cycle
            )
            present = {path.resolve() for path in stable_files}
            for raw_file in stable_files:
                reason = _sample_ignore_reason(
                    raw_file, sample_regex, config.watcher.project_id
                )
                if reason:
                    print(_ignored_line(raw_file.name, reason))
                    continue
                twin = _unprefixed_twin_present(raw_file, present)
                if twin is not None:
                    _note_same_run_skip(raw_file, twin, announced_same_run)
                    continue
                if force_reprocess and raw_file in forced_enqueued:
                    continue
                if not state_store.should_process(raw_file):
                    if not force_reprocess:
                        other = state_store.same_run_block(raw_file)
                        if other is not None:
                            _note_same_run_skip(raw_file, other, announced_same_run)
                    continue
                queue.enqueue(raw_file)
                if force_reprocess:
                    forced_enqueued.add(raw_file)

            batch: list[Path] = []
            while queue.has_pending():
                raw_file = queue.dequeue()
                if raw_file is None:
                    break
                batch.append(raw_file)

            total = len(batch)
            finished = skipped = failed = 0
            synthesized_this_cycle = False
            if total and sys.stderr.isatty():
                file_iter = tqdm(
                    batch, total=total, unit="file", desc="Processing raw files"
                )
            else:
                file_iter = batch
            for index, raw_file in enumerate(file_iter, start=1):
                if stop_event is not None and stop_event.is_set():
                    left = total - index + 1
                    print(f"Stop requested. {left} files left in this batch.")
                    break

                print(raw_file.name)
                if (
                    config.search_space.mode == "untargeted"
                    and not config.search_space.csv_path.exists()
                    and state_store.get_attempts(raw_file) > retry_policy.max_retries
                ):
                    print(
                        f"Skipped {raw_file.name}: too many attempts "
                        "to build the search space"
                    )
                    skipped += 1
                    continue
                try:
                    bootstrap_polarity = _ensure_untargeted_search_space(
                        config=config,
                        raw_file=raw_file,
                        expected_polarity=state_store.get_run_polarity(),
                    )
                except Exception as exc:
                    state_store.mark_in_progress(raw_file)
                    state_store.mark_failed(
                        raw_file, f"untargeted search space build failed: {exc}"
                    )
                    message = str(exc)
                    if is_polarity_mismatch_error(message):
                        print(_polarity_skip_line(raw_file.name, message))
                        skipped += 1
                    else:
                        print(f"Failed {raw_file.name}: {message}")
                        failed += 1
                    continue

                polarity_before = state_store.get_run_polarity()
                if bootstrap_polarity and polarity_before is None:
                    state_store.set_run_polarity(bootstrap_polarity)

                result = _process_one(
                    raw_file=raw_file,
                    orchestrator=orchestrator,
                    retry_policy=retry_policy,
                    state_store=state_store,
                    output_tracker=output_tracker,
                )
                locked = (
                    polarity_before is None
                    and state_store.get_run_polarity() is not None
                )
                outcome = _announce_result(result, locked=locked)
                if outcome == "finished":
                    finished += 1
                elif outcome == "skipped":
                    skipped += 1
                else:
                    failed += 1

                # Refresh HTML + wide CSV exports immediately after each completed
                # sample (same artifacts the end-of-batch synthesizer would write).
                if result.status == "completed":
                    _run_synthesis(synthesizer, output_tracker)
                    synthesized_this_cycle = True

            # Debounced residual (e.g. late-settling events); also covers --once
            # when no sample completed this pass but prior outputs still need a
            # rebuild of dashboard/exports.
            should_synthesize = output_tracker.synthesis_due() or (
                once and total > 0 and not synthesized_this_cycle
            )
            if should_synthesize:
                _run_synthesis(synthesizer, output_tracker)
                synthesized_this_cycle = True

            if stop_event is not None and stop_event.is_set():
                print("Stop requested.")
                return 0

            if not once:
                now = time.monotonic()
                if batch:
                    message = _idle_message(
                        announced=False,
                        elapsed_sec=0,
                        finished=finished,
                        skipped=skipped,
                        failed=failed,
                    )
                else:
                    elapsed = now - last_idle_log if idle_announced else 0
                    message = _idle_message(
                        announced=idle_announced,
                        elapsed_sec=elapsed,
                        finished=0,
                        skipped=0,
                        failed=0,
                    )
                if message:
                    print(message)
                    idle_announced = True
                    last_idle_log = now

            if once:
                break

            if discovery_mode == "watchdog" and observer is not None:
                # Wake early when FS events arrive; still tick for stability.
                observer.event.wait(timeout=1.0)
                observer.event.clear()
                if stop_event is not None and stop_event.is_set():
                    print("Stop requested.")
                    return 0
            else:
                if _wait_for_poll(config.watcher.poll_interval_sec, stop_event):
                    print("Stop requested.")
                    return 0

        return 0
    finally:
        if observer is not None:
            observer.stop()


def run_process_mode(config: PipelineConfig, raw_file: Path) -> int:
    """Process a single raw file (CLI `--mode process`) and synthesize.

    Parameters
    ----------
    config : PipelineConfig
        Resolved pipeline configuration.
    raw_file : Path
        Path to the `.raw` file to process.

    Returns
    -------
    int
        Exit code.
    """

    (
        orchestrator,
        retry_policy,
        _,
        _,
        state_store,
        output_tracker,
        synthesizer,
    ) = _build_runtime(config)
    try:
        sample_regex = _compile_sample_regex(config.watcher.sample_name_regex)
    except re.error as exc:
        print(f"Invalid watcher.sample_name_regex: {exc}")
        return 2

    try:
        configured_polarity = apply_configured_polarity(config, state_store)
    except ValueError as exc:
        print(exc)
        return 2

    print(f"Processing {raw_file.name}.")
    print(f"Output: {config.processor.output_dir}")
    if configured_polarity:
        print(f"Run locked to {configured_polarity}.")
    elif state_store.get_run_polarity():
        print(f"Run locked to {state_store.get_run_polarity()}.")

    synthesizer.write_placeholder_if_missing()
    print(f"Dashboard: {_clickable_path(config.synthesizer.html_output)}")

    if not raw_file.exists():
        print(f"Raw file missing: {raw_file}")
        return 1

    reason = _sample_ignore_reason(raw_file, sample_regex, config.watcher.project_id)
    if reason:
        print(_ignored_line(raw_file.name, reason))
        return 0

    if (
        config.search_space.mode == "untargeted"
        and not config.search_space.csv_path.exists()
        and state_store.get_attempts(raw_file) > retry_policy.max_retries
    ):
        print(
            f"Skipped {raw_file.name}: too many attempts to build the search space"
        )
        return 1

    try:
        bootstrap_polarity = _ensure_untargeted_search_space(
            config=config,
            raw_file=raw_file,
            expected_polarity=state_store.get_run_polarity(),
        )
    except Exception as exc:
        state_store.mark_in_progress(raw_file)
        state_store.mark_failed(
            raw_file, f"untargeted search space build failed: {exc}"
        )
        message = str(exc)
        if is_polarity_mismatch_error(message):
            print(_polarity_skip_line(raw_file.name, message))
        else:
            print(f"Failed {raw_file.name}: {message}")
        return 1

    polarity_before = state_store.get_run_polarity()
    if bootstrap_polarity and polarity_before is None:
        state_store.set_run_polarity(bootstrap_polarity)

    result = _process_one(
        raw_file=raw_file,
        orchestrator=orchestrator,
        retry_policy=retry_policy,
        state_store=state_store,
        output_tracker=output_tracker,
    )
    locked = polarity_before is None and state_store.get_run_polarity() is not None
    _announce_result(result, locked=locked)

    # Rebuild dashboard HTML and wide pivot CSVs after every process run.
    _run_synthesis(synthesizer, output_tracker)
    return 0 if result.status == "completed" else 1


def parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse CLI arguments for the pipeline entrypoint.

    Parameters
    ----------
    argv : list[str]
        List of CLI arguments (excluding program name).

    Returns
    -------
    argparse.Namespace
        Parsed arguments.
    """

    parser = argparse.ArgumentParser(
        description=(
            "MetabWatch: LC–MS QC watcher/processor pipeline. "
            "Prefer --method/--search/--input/--output for standard runs; "
            "use --config for advanced JSON."
        )
    )
    parser.add_argument("--mode", choices=["watch", "process"], default="watch")
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Advanced JSON config path (simplified or legacy nested)",
    )
    method_help = "; ".join(
        f"{key} = {PRESET_SPECS[key]['display_name']}" for key in METHOD_KEYS
    )
    parser.add_argument(
        "--method",
        choices=list(METHOD_KEYS),
        default=None,
        help=f"Method preset: {method_help}",
    )
    parser.add_argument(
        "--search",
        choices=["targeted", "untargeted"],
        default=None,
        help="Search mode for a standard preset run",
    )
    parser.add_argument(
        "--input",
        "-i",
        type=Path,
        default=None,
        help="Input folder of Thermo .raw files (preset path)",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=None,
        help="Output folder for results (preset path)",
    )
    parser.add_argument("--raw", type=Path, default=None, help="Raw file for process mode")
    parser.add_argument("--once", action="store_true", help="Run one watch iteration and exit")
    parser.add_argument(
        "--force-reprocess",
        action="store_true",
        help="Reprocess existing files even when manifest marks them completed (watch mode)",
    )
    parser.add_argument(
        "--polarity",
        choices=["positive", "negative"],
        default=None,
        help=(
            "Optional run polarity for a preset run. Omit to lock from the "
            "first successful sample. For --config, set polarity in the JSON."
        ),
    )
    parser.add_argument(
        "--project-id",
        default=None,
        dest="project_id",
        help=(
            "Optional filename-stem substring (batch / project). Combined "
            "with the preset sample-name filter (QC_Metab_ / Pool). Omit or "
            "leave empty for no extra filter. For --config, set project_id "
            "in the JSON."
        ),
    )
    return parser.parse_args(argv)


def resolve_config_from_args(args: argparse.Namespace) -> PipelineConfig:
    """Build a PipelineConfig from either preset flags or --config.

    Raises
    ------
    ValueError
        If flags are missing, mixed, or otherwise invalid.
    """
    preset_fields = [args.method, args.search, args.input, args.output]
    using_preset = any(value is not None for value in preset_fields)
    using_config = args.config is not None

    if using_preset and using_config:
        raise ValueError(
            "Use either --config OR (--method --search --input --output), not both."
        )
    if using_config:
        if args.polarity is not None:
            raise ValueError(
                "Use --polarity with preset flags, or set polarity in the JSON."
            )
        if args.project_id is not None:
            raise ValueError(
                "Use --project-id with preset flags, or set project_id in the JSON."
            )
        return load_pipeline_config(args.config)
    if using_preset:
        missing = [
            name
            for name, val in (
                ("--method", args.method),
                ("--search", args.search),
                ("--input", args.input),
                ("--output", args.output),
            )
            if val is None
        ]
        if missing:
            raise ValueError(
                "Preset mode requires --method, --search, --input, and --output. "
                f"Missing: {', '.join(missing)}"
            )
        return build_pipeline_config(
            args.method,
            args.search,
            args.input,
            args.output,
            polarity=args.polarity,
            project_id=args.project_id or "",
        )
    raise ValueError(
        "Provide --method/--search/--input/--output for a standard run, "
        "or --config path.json for an advanced config."
    )


def main(argv: list[str] | None = None) -> int:
    """Main entrypoint for running the pipeline.

    Parameters
    ----------
    argv : list[str] | None
        Argument vector to parse (defaults to process argv).

    Returns
    -------
    int
        Exit code.
    """

    args = parse_args(argv or sys.argv[1:])
    try:
        config = resolve_config_from_args(args)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.mode == "process":
        if args.raw is None:
            print("--raw required when --mode process")
            return 2
        return run_process_mode(config=config, raw_file=args.raw)

    try:
        return run_watch_mode(
            config=config,
            once=args.once,
            force_reprocess=args.force_reprocess,
        )
    except KeyboardInterrupt:
        print("\nStop requested.")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
