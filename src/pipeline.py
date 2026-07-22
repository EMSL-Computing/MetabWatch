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
from metabwatch.pipeline_queue import ProcessingQueue
from metabwatch.presets import build_pipeline_config
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


def _sample_allowed(raw_file: Path, sample_regex: re.Pattern[str] | None) -> bool:
    """Return True when a sample should be processed under regex gating."""
    if sample_regex is None:
        return True
    return bool(sample_regex.search(raw_file.stem))


def _clickable_path(path: Path) -> str:
    """Return an OSC-8 terminal hyperlink for a filesystem path.

    Parameters
    ----------
    path : Path
        Path to make clickable in terminals that support OSC-8 links.

    Returns
    -------
    str
        A string containing the OSC-8 escape sequences wrapping the path.
    """

    abs_path = path.resolve()
    uri = f"file://{quote(str(abs_path))}"
    label = str(abs_path)
    return f"\033]8;;{uri}\033\\{label}\033]8;;\033\\"


def _is_polarity_mismatch(error: str | None) -> bool:
    """Return True when an error message indicates a polarity lock failure."""
    return bool(error) and "polarity mismatch" in error.lower()


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
    export_labels = ", ".join(sorted(synthesizer.last_export_paths))
    print(
        "[synthesized] Dashboard: "
        f"{_clickable_path(html_path)} "
        f"(compound pages: {synthesizer.last_compound_pages}, "
        f"skipped samples: {synthesizer.last_skipped_samples}, "
        f"exports: {export_labels or 'none'})"
    )
    for label, export_path in sorted(synthesizer.last_export_paths.items()):
        print(f"[export] {label}: {_clickable_path(export_path)}")
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
            was_unlocked = state_store.get_run_polarity() is None
            state_store.mark_completed(
                raw_file=raw_file,
                output_csv=result.output_csv,
                trace_csv=result.trace_csv,
                acquisition_time=result.acquisition_time,
                polarity=result.polarity,
            )
            if was_unlocked and result.polarity:
                print(
                    f"[polarity] run locked to {state_store.get_run_polarity()} "
                    f"(from {raw_file.name})"
                )
            output_tracker.register_new_output()
            print(f"[completed] {raw_file.name} rows={result.rows}")
            return result

        state_store.mark_failed(raw_file, result.error or "unknown error")
        can_retry = result.retryable and attempts <= retry_policy.max_retries
        print(f"[failed] {raw_file.name} retryable={result.retryable} attempt={attempts} error={result.error}")

        if not can_retry:
            return result

        time.sleep(backoff)
        backoff = backoff * retry_policy.backoff_multiplier


def _discovery_mode_description(discovery_mode: str, poll_interval_sec: float) -> str:
    if discovery_mode == "hybrid":
        return (
            f"discovery_mode=hybrid (watchdog + fallback poll every "
            f"{poll_interval_sec}s)"
        )
    if discovery_mode == "watchdog":
        return "discovery_mode=watchdog (FS events + startup scan)"
    return f"discovery_mode=poll (directory scan every {poll_interval_sec}s)"


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
            "Use Stop in the GUI to exit."
            if stop_event is not None
            else "Press Ctrl+C to exit."
        )
        print(
            "[watching] Monitoring for stable .raw files "
            f"in {config.watcher.raw_dir} "
            f"({_discovery_mode_description(discovery_mode, config.watcher.poll_interval_sec)}). "
            f"{stop_hint}"
        )

        if state_store.get_run_polarity():
            print(
                f"[polarity] run locked to {state_store.get_run_polarity()} (from manifest)"
            )

        polarity_hard_stop_once = False
        forced_enqueued: set[Path] = set()

        # Startup reconciliation: files written while MetabWatch was offline.
        reconcile_files = watcher.list_current_raw_files()
        watcher.register_many(reconcile_files)

        if force_reprocess or not state_store.has_entries():
            bootstrap_files = reconcile_files
            if bootstrap_files:
                if force_reprocess:
                    print(
                        f"[bootstrap] force-reprocess enabled; enqueueing "
                        f"{len(bootstrap_files)} existing raw files"
                    )
                else:
                    print(
                        f"[bootstrap] first run detected; enqueueing "
                        f"{len(bootstrap_files)} existing raw files"
                    )
            for raw_file in bootstrap_files:
                if not _sample_allowed(raw_file, sample_regex):
                    print(f"[ignored] {raw_file.name} (sample_name_regex no match)")
                    continue
                if force_reprocess or state_store.should_process(raw_file):
                    queue.enqueue(raw_file)
                    forced_enqueued.add(raw_file)

        state_store.recover_stale_in_progress()

        while True:
            if stop_event is not None and stop_event.is_set():
                print("[stopped] Stop requested.")
                return 0

            if observer is not None:
                watcher.register_many(observer.drain())

            for raw_file in watcher.get_stable_new_files(
                scan_directory=scan_each_cycle
            ):
                if not _sample_allowed(raw_file, sample_regex):
                    print(f"[ignored] {raw_file.name} (sample_name_regex no match)")
                    continue
                if force_reprocess and raw_file in forced_enqueued:
                    continue
                if not state_store.should_process(raw_file):
                    if force_reprocess:
                        continue
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
            synthesized_this_cycle = False
            mismatch_in_batch = False
            for index, raw_file in enumerate(
                tqdm(batch, total=total, unit="file", desc="Processing raw files"),
                start=1,
            ):
                if stop_event is not None and stop_event.is_set():
                    print(
                        f"[stopped] Stop requested; "
                        f"skipping {total - index + 1} remaining file(s) in batch."
                    )
                    break

                if mismatch_in_batch:
                    remaining = total - index + 1
                    print(
                        f"[polarity] hard-stop: skipping {remaining} remaining "
                        "file(s) in this batch due to mixed polarity"
                    )
                    for skipped in batch[index - 1 :]:
                        print(
                            f"[skipped] {skipped.name} "
                            "(polarity hard-stop after mixed polarity)"
                        )
                    break

                print(f"[processing {index}/{total}] {raw_file.name}")
                if (
                    config.search_space.mode == "untargeted"
                    and not config.search_space.csv_path.exists()
                    and state_store.get_attempts(raw_file) > retry_policy.max_retries
                ):
                    print(
                        f"[skipped] {raw_file.name} exceeded max_retries "
                        f"({retry_policy.max_retries}) on untargeted search space build"
                    )
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
                    print(
                        f"[failed] {raw_file.name} untargeted search space build: {exc}"
                    )
                    if _is_polarity_mismatch(str(exc)):
                        mismatch_in_batch = True
                        polarity_hard_stop_once = True
                    continue

                if bootstrap_polarity and state_store.get_run_polarity() is None:
                    state_store.set_run_polarity(bootstrap_polarity)
                    print(
                        f"[polarity] run locked to {state_store.get_run_polarity()} "
                        f"(from {raw_file.name})"
                    )

                result = _process_one(
                    raw_file=raw_file,
                    orchestrator=orchestrator,
                    retry_policy=retry_policy,
                    state_store=state_store,
                    output_tracker=output_tracker,
                )

                if result.status != "completed" and _is_polarity_mismatch(result.error):
                    mismatch_in_batch = True
                    polarity_hard_stop_once = True

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
                print("[stopped] Stop requested.")
                return 0

            if synthesized_this_cycle and not once:
                print(
                    f"[watching] Waiting for new stable .raw files. {stop_hint}"
                )
            elif not batch and not once:
                print(
                    f"[watching] No new stable .raw files yet. {stop_hint}"
                )

            if once:
                break

            if discovery_mode == "watchdog" and observer is not None:
                # Wake early when FS events arrive; still tick for stability.
                observer.event.wait(timeout=1.0)
                observer.event.clear()
                if stop_event is not None and stop_event.is_set():
                    print("[stopped] Stop requested.")
                    return 0
            else:
                if _wait_for_poll(config.watcher.poll_interval_sec, stop_event):
                    print("[stopped] Stop requested.")
                    return 0

        if once and polarity_hard_stop_once:
            return 1
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

    if not raw_file.exists():
        print(f"Raw file missing: {raw_file}")
        return 1

    if not _sample_allowed(raw_file, sample_regex):
        print(f"[ignored] {raw_file.name} (sample_name_regex no match)")
        return 0

    if (
        config.search_space.mode == "untargeted"
        and not config.search_space.csv_path.exists()
        and state_store.get_attempts(raw_file) > retry_policy.max_retries
    ):
        print(
            f"[skipped] {raw_file.name} exceeded max_retries "
            f"({retry_policy.max_retries}) on untargeted search space build"
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
        print(f"[failed] {raw_file.name} untargeted search space build: {exc}")
        return 1

    if bootstrap_polarity and state_store.get_run_polarity() is None:
        state_store.set_run_polarity(bootstrap_polarity)
        print(
            f"[polarity] run locked to {state_store.get_run_polarity()} "
            f"(from {raw_file.name})"
        )

    result = _process_one(
        raw_file=raw_file,
        orchestrator=orchestrator,
        retry_policy=retry_policy,
        state_store=state_store,
        output_tracker=output_tracker,
    )

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
    parser.add_argument(
        "--method",
        choices=["rp_metab_pnnl", "hilic_metab_pnnl"],
        default=None,
        help=(
            "Method preset: hilic_metab_pnnl = PNNL Standard HILIC Metabolomics Method; "
            "rp_metab_pnnl = PNNL Standard RP Metabolomics Method"
        ),
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
        print("\n[stopped] Watch mode interrupted by user (Ctrl+C).")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
