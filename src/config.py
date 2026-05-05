from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ProcessorConfig:
    standards_csv: Path
    params_path: Path
    output_dir: Path
    mz_tolerance_ppm: float = 5.0
    rt_tolerance: float = 0.5
    min_area: float = 5e3
    plot_eics: bool = False
    plot_tic: bool = True


@dataclass(frozen=True)
class WatcherConfig:
    raw_dir: Path
    poll_interval_sec: float = 10.0
    stability_wait_sec: float = 20.0


@dataclass(frozen=True)
class StateConfig:
    pipeline_manifest: Path
    stale_in_progress_sec: int = 3600


@dataclass(frozen=True)
class SynthesizerConfig:
    html_output: Path
    output_dir: Path
    debounce_sec: float = 5.0


@dataclass(frozen=True)
class PipelineConfig:
    processor: ProcessorConfig
    watcher: WatcherConfig
    state: StateConfig
    synthesizer: SynthesizerConfig
    max_retries: int = 3
    initial_backoff_sec: float = 10.0
    backoff_multiplier: float = 2.0


def load_pipeline_config(config_path: Path, repo_root: Path) -> PipelineConfig:
    with config_path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)

    processor = payload.get("processor", {})
    watcher = payload.get("watcher", {})
    synthesizer = payload.get("synthesizer", {})

    output_dir = repo_root / processor["output_dir"]

    return PipelineConfig(
        processor=ProcessorConfig(
            standards_csv=repo_root / processor["standards_csv"],
            params_path=repo_root / processor["params_path"],
            output_dir=output_dir,
            mz_tolerance_ppm=float(processor.get("mz_tolerance_ppm", 5.0)),
            rt_tolerance=float(processor.get("rt_tolerance", 0.5)),
            min_area=float(processor.get("min_area", 5e3)),
            plot_eics=bool(processor.get("plot_eics", False)),
            plot_tic=bool(processor.get("plot_tic", True)),
        ),
        watcher=WatcherConfig(
            raw_dir=repo_root / watcher["raw_dir"],
            poll_interval_sec=float(watcher.get("poll_interval_sec", 10.0)),
            stability_wait_sec=float(watcher.get("stability_wait_sec", 20.0)),
        ),
        state=StateConfig(
            pipeline_manifest=output_dir / "pipeline_manifest.json",
            stale_in_progress_sec=int(payload.get("stale_in_progress_sec", 3600)),
        ),
        synthesizer=SynthesizerConfig(
            html_output=output_dir / "dashboard.html",
            output_dir=output_dir,
            debounce_sec=float(synthesizer.get("debounce_sec", 5.0)),
        ),
        max_retries=int(payload.get("max_retries", 3)),
        initial_backoff_sec=float(payload.get("initial_backoff_sec", 10.0)),
        backoff_multiplier=float(payload.get("backoff_multiplier", 2.0)),
    )
