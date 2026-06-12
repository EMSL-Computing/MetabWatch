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
    integrate_mass_features : bool
        Whether to run CoreMS mass-feature integration.
    cluster_mass_features : bool
        Whether to run CoreMS mass-feature clustering.
    """
    standards_csv: Path
    params_path: Path
    output_dir: Path
    mz_tolerance_ppm: float = 5.0
    rt_tolerance: float = 0.5
    min_area: float = 5e3
    plot_eics: bool = False
    plot_tic: bool = True
    integrate_mass_features: bool = False
    cluster_mass_features: bool = False


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
class SearchSpaceConfig:
    """Configuration for the search-space source.

    Parameters
    ----------
    mode : str
        Either "targeted" (use processor.standards_csv) or "untargeted"
        (build a top-N peak list from the first matching sample and persist
        it to `csv_path`).
    top_n : int
        Number of peaks to keep when mode == "untargeted". Ignored otherwise.
    csv_path : Path
        On-disk location of the search-space CSV. In targeted mode this is
        identical to processor.standards_csv. In untargeted mode this is
        always `<processor.output_dir>/untargeted_search_space.csv`.
    """

    mode: str
    top_n: int
    csv_path: Path


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
    search_space : SearchSpaceConfig
        Search-space source configuration.
    """
    processor: ProcessorConfig
    watcher: WatcherConfig
    state: StateConfig
    synthesizer: SynthesizerConfig
    search_space: SearchSpaceConfig
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

    search_space_payload = payload.get("search_space", {}) or {}
    mode = str(search_space_payload.get("mode", "targeted")).strip().lower()
    if mode not in {"targeted", "untargeted"}:
        raise ValueError(
            f"search_space.mode must be 'targeted' or 'untargeted', got '{mode}'"
        )
    top_n = int(search_space_payload.get("top_n", 100))
    if mode == "untargeted" and top_n <= 0:
        raise ValueError("search_space.top_n must be > 0 when mode is 'untargeted'")

    standards_csv_value = processor.get("standards_csv")
    if mode == "untargeted":
        search_space_csv = output_dir / "untargeted_search_space.csv"
        if standards_csv_value is None:
            standards_csv_path = search_space_csv
        else:
            standards_csv_path = repo_root / standards_csv_value
    else:
        if standards_csv_value is None:
            raise ValueError(
                "processor.standards_csv is required when search_space.mode is 'targeted'"
            )
        standards_csv_path = repo_root / standards_csv_value
        search_space_csv = standards_csv_path

    return PipelineConfig(
        processor=ProcessorConfig(
            standards_csv=standards_csv_path,
            params_path=repo_root / processor["params_path"],
            output_dir=output_dir,
            mz_tolerance_ppm=float(processor.get("mz_tolerance_ppm", 5.0)),
            rt_tolerance=float(processor.get("rt_tolerance", 0.5)),
            min_area=float(processor.get("min_area", 5e3)),
            plot_eics=bool(processor.get("plot_eics", False)),
            plot_tic=bool(processor.get("plot_tic", True)),
            integrate_mass_features=bool(processor.get("integrate_mass_features", False)),
            cluster_mass_features=bool(processor.get("cluster_mass_features", False)),
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
        search_space=SearchSpaceConfig(
            mode=mode,
            top_n=top_n,
            csv_path=search_space_csv,
        ),
        max_retries=int(payload.get("max_retries", 3)),
        initial_backoff_sec=float(payload.get("initial_backoff_sec", 10.0)),
        backoff_multiplier=float(payload.get("backoff_multiplier", 2.0)),
    )
