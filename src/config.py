from __future__ import annotations

"""Pipeline configuration models and loader.

This module defines the dataclasses used to configure the pipeline runtime and
provides a loader to read a JSON configuration file and resolve repository
relative paths to absolute `pathlib.Path` objects.
"""

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ProcessorConfig:
    """Configuration for the processing step.

    Parameters
    ----------
    standards_csv : Path
        Path to the standards CSV used for targeted matching.
    params_path : Path
        Path to the CoreMS TOML parameter file.
    output_dir : Path
        Directory where outputs (CSVs, plots) will be written.
    mz_tolerance_ppm : float
        m/z matching tolerance in ppm.
    rt_tolerance : float
        Retention time tolerance in minutes.
    min_area : float
        Minimum peak area threshold.
    plot_eics : bool
        Whether to generate EIC plots.
    plot_tic : bool
        Whether to generate a TIC plot.
    """
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
    """Configuration for the raw-file watcher.

    Parameters
    ----------
    raw_dir : Path
        Directory to poll for incoming `.raw` files.
    poll_interval_sec : float
        Seconds between poll cycles.
    stability_wait_sec : float
        Number of seconds a file must remain unchanged to be treated as stable.
    sample_name_regex : str | None
        Optional regex applied to raw filename stem to decide processing.
    """
    raw_dir: Path
    poll_interval_sec: float = 10.0
    stability_wait_sec: float = 20.0
    sample_name_regex: str | None = None


@dataclass(frozen=True)
class StateConfig:
    """Configuration for persistent pipeline state.

    Parameters
    ----------
    pipeline_manifest : Path
        Path to the pipeline manifest JSON used for idempotency and tracking.
    stale_in_progress_sec : int
        Seconds after which an `in_progress` entry is considered stale.
    """
    pipeline_manifest: Path
    stale_in_progress_sec: int = 3600


@dataclass(frozen=True)
class SynthesizerConfig:
    """Configuration for HTML synthesizer behavior.

    Parameters
    ----------
    html_output : Path
        Path where the dashboard HTML will be written.
    output_dir : Path
        Directory containing per-sample outputs to aggregate.
    debounce_sec : float
        Debounce interval (seconds) before regenerating the dashboard.
    mz_tolerance_ppm : float
        m/z tolerance used when drawing landing QC summary ranges.
    rt_tolerance : float
        Retention-time tolerance used when drawing landing QC summary ranges.
    """
    html_output: Path
    output_dir: Path
    debounce_sec: float = 5.0
    mz_tolerance_ppm: float = 5.0
    rt_tolerance: float = 0.5


@dataclass(frozen=True)
class PipelineConfig:
    """Top-level pipeline configuration container.

    Attributes
    ----------
    processor : ProcessorConfig
        Processor-specific configuration.
    watcher : WatcherConfig
        Watcher-specific configuration.
    state : StateConfig
        Persistence/state configuration.
    synthesizer : SynthesizerConfig
        Dashboard generation configuration.
    """
    processor: ProcessorConfig
    watcher: WatcherConfig
    state: StateConfig
    synthesizer: SynthesizerConfig
    max_retries: int = 3
    initial_backoff_sec: float = 10.0
    backoff_multiplier: float = 2.0


def load_pipeline_config(config_path: Path, repo_root: Path) -> PipelineConfig:
    """Load pipeline configuration from a JSON file.

    The JSON structure mirrors the dataclass layout under top-level keys
    such as `processor`, `watcher`, and `synthesizer`. Relative paths in the
    JSON are resolved against `repo_root`.

    Parameters
    ----------
    config_path : Path
        Path to the JSON configuration file.
    repo_root : Path
        Repository root used to resolve relative paths present in the JSON.

    Returns
    -------
    PipelineConfig
        Fully resolved pipeline configuration.
    """

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
            sample_name_regex=watcher.get("sample_name_regex"),
        ),
        state=StateConfig(
            pipeline_manifest=output_dir / "pipeline_manifest.json",
            stale_in_progress_sec=int(payload.get("stale_in_progress_sec", 3600)),
        ),
        synthesizer=SynthesizerConfig(
            html_output=output_dir / "dashboard.html",
            output_dir=output_dir,
            debounce_sec=float(synthesizer.get("debounce_sec", 5.0)),
            mz_tolerance_ppm=float(processor.get("mz_tolerance_ppm", 5.0)),
            rt_tolerance=float(processor.get("rt_tolerance", 0.5)),
        ),
        max_retries=int(payload.get("max_retries", 3)),
        initial_backoff_sec=float(payload.get("initial_backoff_sec", 10.0)),
        backoff_multiplier=float(payload.get("backoff_multiplier", 2.0)),
    )
