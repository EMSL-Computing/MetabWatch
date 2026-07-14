from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path
from urllib.parse import quote

from config import PipelineConfig, load_pipeline_config
from output import OutputTracker
from pipeline_queue import ProcessingQueue
from processor import (
    ProcessResult,
    ProcessorOrchestrator,
    RetryPolicy,
    build_untargeted_search_space,
)
from state import ManifestStateStore
from synthesis import HTMLSynthesizer
from watcher import RawFileWatcher

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


def _ensure_untargeted_search_space(
    config: PipelineConfig,
    raw_file: Path,
) -> None:
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
    """
    if config.search_space.mode != "untargeted":
        return
    if config.search_space.csv_path.exists():
        return

    print(
        f"[untargeted] building search space from {raw_file.name} "
        f"(top_n={config.search_space.top_n})"
    )
    build_untargeted_search_space(
        raw_file=raw_file,
        params_path=config.processor.params_path,
        output_csv=config.search_space.csv_path,
        top_n=config.search_space.top_n,
        mz_tolerance_ppm=config.processor.mz_tolerance_ppm,
    )


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
    based on the provided `RetryPolicy`.

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
        result = orchestrator.process_single_raw(raw_file)
        if result.status == "completed":
            state_store.mark_completed(
                raw_file=raw_file,
                output_csv=result.output_csv,
                trace_csv=result.trace_csv,
                acquisition_time=result.acquisition_time,
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


def run_watch_mode(
    config: PipelineConfig,
    once: bool = False,
    force_reprocess: bool = False,
) -> int:
    """Run the watch loop: discover, enqueue, process, and synthesize.

    Parameters
    ----------
    config : PipelineConfig
        Resolved pipeline configuration.
    once : bool, optional
        If True, performs a single iteration and exits.

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

    print(
        "[watching] Monitoring for stable .raw files "
        f"in {config.watcher.raw_dir}. Press Ctrl+C to exit."
    )

    forced_enqueued: set[Path] = set()

    if force_reprocess or not state_store.has_entries():
        bootstrap_files = watcher.list_current_raw_files()
        if bootstrap_files:
            if force_reprocess:
                print(f"[bootstrap] force-reprocess enabled; enqueueing {len(bootstrap_files)} existing raw files")
            else:
                print(f"[bootstrap] first run detected; enqueueing {len(bootstrap_files)} existing raw files")
        for raw_file in bootstrap_files:
            if not _sample_allowed(raw_file, sample_regex):
                print(f"[ignored] {raw_file.name} (sample_name_regex no match)")
                continue
            if force_reprocess or state_store.should_process(raw_file):
                queue.enqueue(raw_file)
                forced_enqueued.add(raw_file)

    state_store.recover_stale_in_progress()

    while True:
        for raw_file in watcher.get_stable_new_files():
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
        for index, raw_file in enumerate(
            tqdm(batch, total=total, unit="file", desc="Processing raw files"),
            start=1,
        ):
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
                _ensure_untargeted_search_space(config=config, raw_file=raw_file)
            except Exception as exc:
                state_store.mark_in_progress(raw_file)
                state_store.mark_failed(
                    raw_file, f"untargeted search space build failed: {exc}"
                )
                print(
                    f"[failed] {raw_file.name} untargeted search space build: {exc}"
                )
                continue
            result = _process_one(
                raw_file=raw_file,
                orchestrator=orchestrator,
                retry_policy=retry_policy,
                state_store=state_store,
                output_tracker=output_tracker,
            )
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

        if synthesized_this_cycle and not once:
            print("[watching] Waiting for new stable .raw files. Press Ctrl+C to exit.")
        elif not batch and not once:
            print("[watching] No new stable .raw files yet. Press Ctrl+C to exit.")

        if once:
            break

        time.sleep(config.watcher.poll_interval_sec)

    return 0


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
        _ensure_untargeted_search_space(config=config, raw_file=raw_file)
    except Exception as exc:
        state_store.mark_in_progress(raw_file)
        state_store.mark_failed(
            raw_file, f"untargeted search space build failed: {exc}"
        )
        print(f"[failed] {raw_file.name} untargeted search space build: {exc}")
        return 1

    _process_one(
        raw_file=raw_file,
        orchestrator=orchestrator,
        retry_policy=retry_policy,
        state_store=state_store,
        output_tracker=output_tracker,
    )

    # Rebuild dashboard HTML and wide pivot CSVs after every process run.
    _run_synthesis(synthesizer, output_tracker)
    return 0


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

    parser = argparse.ArgumentParser(description="LCMS QC watcher/processor pipeline")
    parser.add_argument("--mode", choices=["watch", "process"], default="watch")
    parser.add_argument("--config", type=Path, required=True, help="Required JSON config path")
    parser.add_argument("--raw", type=Path, default=None, help="Raw file for process mode")
    parser.add_argument("--once", action="store_true", help="Run one watch iteration and exit")
    parser.add_argument(
        "--force-reprocess",
        action="store_true",
        help="Reprocess existing files even when manifest marks them completed (watch mode)",
    )
    return parser.parse_args(argv)


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
    repo_root = Path(__file__).resolve().parent.parent
    config = load_pipeline_config(args.config, repo_root=repo_root)

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
