from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from urllib.parse import quote

from config import PipelineConfig, load_pipeline_config
from output import OutputTracker
from pipeline_queue import ProcessingQueue
from processor import ProcessResult, ProcessorOrchestrator, RetryPolicy
from state import ManifestStateStore
from synthesis import HTMLSynthesizer
from watcher import RawFileWatcher

try:
    from tqdm import tqdm
except ImportError:  # pragma: no cover
    def tqdm(iterable, **_: object):
        return iterable


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
        raw_dirs=(config.watcher.raw_dir,),
        stability_wait_sec=config.watcher.stability_wait_sec,
    )
    queue = ProcessingQueue()
    state_store = ManifestStateStore(
        manifest_json=config.state.pipeline_manifest,
        manifest_csv=None,
        stale_in_progress_sec=config.state.stale_in_progress_sec,
    )
    output_tracker = OutputTracker(debounce_sec=config.synthesizer.debounce_sec)
    synthesizer = HTMLSynthesizer(
        output_dirs=(config.synthesizer.output_dir,),
        html_output=config.synthesizer.html_output,
    )
    return orchestrator, retry_policy, watcher, queue, state_store, output_tracker, synthesizer


def _clickable_path(path: Path) -> str:
    abs_path = path.resolve()
    uri = f"file://{quote(str(abs_path))}"
    label = str(abs_path)
    return f"\033]8;;{uri}\033\\{label}\033]8;;\033\\"


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

    print(
        "[watching] Monitoring for stable .raw files "
        f"in {config.watcher.raw_dir}. Press Ctrl+C to exit."
    )

    if not state_store.has_entries():
        bootstrap_files = watcher.list_current_raw_files()
        if bootstrap_files:
            print(f"[bootstrap] first run detected; enqueueing {len(bootstrap_files)} existing raw files")
        for raw_file in bootstrap_files:
            if state_store.should_process(raw_file):
                queue.enqueue(raw_file)

    state_store.recover_stale_in_progress()

    while True:
        for raw_file in watcher.get_stable_new_files():
            if not state_store.should_process(raw_file):
                continue
            queue.enqueue(raw_file)

        batch: list[Path] = []
        while queue.has_pending():
            raw_file = queue.dequeue()
            if raw_file is None:
                break
            batch.append(raw_file)

        total = len(batch)
        for index, raw_file in enumerate(
            tqdm(batch, total=total, unit="file", desc="Processing raw files"),
            start=1,
        ):
            print(f"[processing {index}/{total}] {raw_file.name}")
            _process_one(
                raw_file=raw_file,
                orchestrator=orchestrator,
                retry_policy=retry_policy,
                state_store=state_store,
                output_tracker=output_tracker,
            )

        if output_tracker.synthesis_due():
            html_path = synthesizer.render()
            print(f"[synthesized] Dashboard: {_clickable_path(html_path)}")
            output_tracker.clear()
            if not once:
                print("[watching] Waiting for new stable .raw files. Press Ctrl+C to exit.")
        elif not batch and not once:
            print("[watching] No new stable .raw files yet. Press Ctrl+C to exit.")

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
    parser.add_argument("--config", type=Path, required=True, help="Required JSON config path")
    parser.add_argument("--raw", type=Path, default=None, help="Raw file for process mode")
    parser.add_argument("--once", action="store_true", help="Run one watch iteration and exit")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    repo_root = Path(__file__).resolve().parent.parent
    config = load_pipeline_config(args.config, repo_root=repo_root)

    if args.mode == "process":
        if args.raw is None:
            print("--raw required when --mode process")
            return 2
        return run_process_mode(config=config, raw_file=args.raw)

    try:
        return run_watch_mode(config=config, once=args.once)
    except KeyboardInterrupt:
        print("\n[stopped] Watch mode interrupted by user (Ctrl+C).")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
