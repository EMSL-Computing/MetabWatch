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
    raw_dirs: tuple[Path, ...]
    poll_interval_sec: float = 10.0
    stability_wait_sec: float = 20.0


@dataclass(frozen=True)
class StateConfig:
    manifest_json: Path
    manifest_csv: Path | None = None
    stale_in_progress_sec: int = 3600


@dataclass(frozen=True)
class SynthesizerConfig:
    html_output: Path
    output_dirs: tuple[Path, ...]
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


def _to_path_tuple(values: list[str]) -> tuple[Path, ...]:
    return tuple(Path(v) for v in values)


def default_pipeline_config(repo_root: Path) -> PipelineConfig:
    return PipelineConfig(
        processor=ProcessorConfig(
            standards_csv=repo_root / "data/qc_search_space/hilic_qc_search.csv",
            params_path=repo_root / "data/corems_params/monet_hilic_corems_lcms_params.toml",
            output_dir=repo_root / "data/results_hilic_pos",
            mz_tolerance_ppm=5.0,
            rt_tolerance=0.5,
            min_area=5e3,
            plot_eics=False,
            plot_tic=True,
        ),
        watcher=WatcherConfig(
            raw_dirs=(repo_root / "data/raw_positive", repo_root / "data/raw_negative"),
            poll_interval_sec=10.0,
            stability_wait_sec=20.0,
        ),
        state=StateConfig(
            manifest_json=repo_root / "data/.state/pipeline_manifest.json",
            manifest_csv=repo_root / "data/.state/pipeline_manifest.csv",
            stale_in_progress_sec=3600,
        ),
        synthesizer=SynthesizerConfig(
            html_output=repo_root / "data/results_hilic_pos/dashboard.html",
            output_dirs=(repo_root / "data/results_hilic_pos",),
            debounce_sec=5.0,
        ),
        max_retries=3,
        initial_backoff_sec=10.0,
        backoff_multiplier=2.0,
    )


def load_pipeline_config(config_path: Path, repo_root: Path) -> PipelineConfig:
    with config_path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)

    processor = payload.get("processor", {})
    watcher = payload.get("watcher", {})
    state = payload.get("state", {})
    synthesizer = payload.get("synthesizer", {})

    return PipelineConfig(
        processor=ProcessorConfig(
            standards_csv=repo_root / processor["standards_csv"],
            params_path=repo_root / processor["params_path"],
            output_dir=repo_root / processor["output_dir"],
            mz_tolerance_ppm=float(processor.get("mz_tolerance_ppm", 5.0)),
            rt_tolerance=float(processor.get("rt_tolerance", 0.5)),
            min_area=float(processor.get("min_area", 5e3)),
            plot_eics=bool(processor.get("plot_eics", False)),
            plot_tic=bool(processor.get("plot_tic", True)),
        ),
        watcher=WatcherConfig(
            raw_dirs=tuple(
                repo_root / p
                for p in watcher.get("raw_dirs", ["data/raw_positive", "data/raw_negative"])
            ),
            poll_interval_sec=float(watcher.get("poll_interval_sec", 10.0)),
            stability_wait_sec=float(watcher.get("stability_wait_sec", 20.0)),
        ),
        state=StateConfig(
            manifest_json=repo_root / state.get("manifest_json", "data/.state/pipeline_manifest.json"),
            manifest_csv=(
                repo_root / state["manifest_csv"] if state.get("manifest_csv") else None
            ),
            stale_in_progress_sec=int(state.get("stale_in_progress_sec", 3600)),
        ),
        synthesizer=SynthesizerConfig(
            html_output=repo_root / synthesizer.get("html_output", "data/results_hilic_pos/dashboard.html"),
            output_dirs=tuple(
                repo_root / p
                for p in synthesizer.get("output_dirs", ["data/results_hilic_pos"])
            ),
            debounce_sec=float(synthesizer.get("debounce_sec", 5.0)),
        ),
        max_retries=int(payload.get("max_retries", 3)),
        initial_backoff_sec=float(payload.get("initial_backoff_sec", 10.0)),
        backoff_multiplier=float(payload.get("backoff_multiplier", 2.0)),
    )
