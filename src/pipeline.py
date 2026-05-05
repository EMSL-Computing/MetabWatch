from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from config import PipelineConfig, default_pipeline_config, load_pipeline_config
from output import OutputTracker
from pipeline_queue import ProcessingQueue
from processor import ProcessResult, ProcessorOrchestrator, RetryPolicy
from state import ManifestStateStore
from synthesis import HTMLSynthesizer
from watcher import RawFileWatcher


def _build_runtime(config: PipelineConfig):
    orchestrator = ProcessorOrchestrator(
        standards_csv=config.processor.standards_csv,
        params_path=config.processor.params_path,
        output_dir=config.processor.output_dir,
        mz_tolerance_ppm=config.processor.mz_tolerance_ppm,
        rt_tolerance=config.processor.rt_tolerance,
        min_area=config.processor.min_area,
        plot_eics=config.processor.plot_eics,
        plot_tic=config.processor.plot_tic,
    )
    retry_policy = RetryPolicy(
        max_retries=config.max_retries,
        initial_backoff_sec=config.initial_backoff_sec,
        backoff_multiplier=config.backoff_multiplier,
    )
    watcher = RawFileWatcher(
        raw_dirs=config.watcher.raw_dirs,
        stability_wait_sec=config.watcher.stability_wait_sec,
    )
    queue = ProcessingQueue()
    state_store = ManifestStateStore(
        manifest_json=config.state.manifest_json,
        manifest_csv=config.state.manifest_csv,
        stale_in_progress_sec=config.state.stale_in_progress_sec,
    )
    output_tracker = OutputTracker(debounce_sec=config.synthesizer.debounce_sec)
    synthesizer = HTMLSynthesizer(
        output_dirs=config.synthesizer.output_dirs,
        html_output=config.synthesizer.html_output,
    )
    return orchestrator, retry_policy, watcher, queue, state_store, output_tracker, synthesizer


def _process_one(
    raw_file: Path,
    orchestrator: ProcessorOrchestrator,
    retry_policy: RetryPolicy,
    state_store: ManifestStateStore,
    output_tracker: OutputTracker,
) -> ProcessResult:
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


def run_watch_mode(config: PipelineConfig, once: bool = False) -> int:
    (
        orchestrator,
        retry_policy,
        watcher,
        queue,
        state_store,
        output_tracker,
        synthesizer,
    ) = _build_runtime(config)

    state_store.recover_stale_in_progress()

    while True:
        for raw_file in watcher.get_stable_new_files():
            if not state_store.should_process(raw_file):
                continue
            queue.enqueue(raw_file)

        while queue.has_pending():
            raw_file = queue.dequeue()
            if raw_file is None:
                break
            _process_one(
                raw_file=raw_file,
                orchestrator=orchestrator,
                retry_policy=retry_policy,
                state_store=state_store,
                output_tracker=output_tracker,
            )

        if output_tracker.synthesis_due():
            html_path = synthesizer.render()
            print(f"[synthesized] {html_path}")
            output_tracker.clear()

        if once:
            break

        time.sleep(config.watcher.poll_interval_sec)

    return 0


def run_process_mode(config: PipelineConfig, raw_file: Path) -> int:
    (
        orchestrator,
        retry_policy,
        _,
        _,
        state_store,
        output_tracker,
        synthesizer,
    ) = _build_runtime(config)

    if not raw_file.exists():
        print(f"Raw file missing: {raw_file}")
        return 1

    _process_one(
        raw_file=raw_file,
        orchestrator=orchestrator,
        retry_policy=retry_policy,
        state_store=state_store,
        output_tracker=output_tracker,
    )

    html_path = synthesizer.render()
    print(f"[synthesized] {html_path}")
    return 0


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="LCMS QC watcher/processor pipeline")
    parser.add_argument("--mode", choices=["watch", "process"], default="watch")
    parser.add_argument("--config", type=Path, default=None, help="Optional JSON config path")
    parser.add_argument("--raw", type=Path, default=None, help="Raw file for process mode")
    parser.add_argument("--once", action="store_true", help="Run one watch iteration and exit")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    repo_root = Path(__file__).resolve().parent.parent

    if args.config:
        config = load_pipeline_config(args.config, repo_root=repo_root)
    else:
        config = default_pipeline_config(repo_root=repo_root)

    if args.mode == "process":
        if args.raw is None:
            print("--raw required when --mode process")
            return 2
        return run_process_mode(config=config, raw_file=args.raw)

    return run_watch_mode(config=config, once=args.once)


if __name__ == "__main__":
    raise SystemExit(main())
