from __future__ import annotations

"""Pipeline configuration models and loader.

This module defines the dataclasses used to configure the pipeline runtime and
provides a loader to read a JSON configuration file and resolve repository
relative paths to absolute `pathlib.Path` objects.

Two JSON shapes are supported:

1. **Simplified** (preferred) — flat top-level keys such as ``input_folder``,
   ``output_folder``, ``corems_params``, ``targeted``, ``qc_compounds``, and
   ``sample_name_regex``.
2. **Legacy nested** — ``processor`` / ``watcher`` / ``search_space`` blocks
   as used by earlier configs.

Both expand into the same :class:`PipelineConfig` runtime model.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ProcessorConfig:
    """Configuration for the processing step.

    Parameters
    ----------
    standards_csv : Path
        Path to the standards CSV used for targeted matching. In untargeted
        mode this field is populated with the derived
        ``<output_dir>/untargeted_search_space.csv`` path and is NOT read by
        the targeted pipeline (the untargeted bootstrap writes to it instead).
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


DISCOVERY_MODES = frozenset({"hybrid", "watchdog", "poll"})


@dataclass(frozen=True)
class WatcherConfig:
    """Configuration for the raw-file watcher.

    Parameters
    ----------
    raw_dir : Path
        Directory to watch for incoming ``.raw`` files.
    poll_interval_sec : float
        Seconds between poll cycles (full-directory scan interval in
        ``poll`` / ``hybrid`` modes; unused for full scans in pure
        ``watchdog`` mode).
    stability_wait_sec : float
        Number of seconds a file must remain unchanged to be treated as stable.
    sample_name_regex : str | None
        Optional regex applied to raw filename stem to decide processing.
    discovery_mode : str
        How new files are discovered: ``hybrid`` (watchdog + fallback poll,
        default), ``watchdog`` (FS events + startup scan only), or ``poll``
        (periodic directory scan only).
    """
    raw_dir: Path
    poll_interval_sec: float = 10.0
    stability_wait_sec: float = 20.0
    sample_name_regex: str | None = None
    discovery_mode: str = "hybrid"


@dataclass(frozen=True)
class StateConfig:
    """Configuration for persistent pipeline state.

    Parameters
    ----------
    pipeline_manifest : Path
        Path to the pipeline manifest JSON used for idempotency and tracking.
    stale_in_progress_sec : int
        Seconds after which an ``in_progress`` entry is considered stale.
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
        it to ``csv_path``).
    top_n : int
        Number of peaks to keep when mode == "untargeted". Ignored otherwise.
    csv_path : Path
        On-disk location of the search-space CSV. In targeted mode this is
        identical to processor.standards_csv. In untargeted mode this is
        always ``<processor.output_dir>/untargeted_search_space.csv``.
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


# Keys that mark the preferred flat simplified schema.
_SIMPLIFIED_MARKERS = frozenset({
    "input_folder",
    "output_folder",
    "corems_params",
    "qc_compounds",
    "targeted",
    "sample_name_regex",
})

# Keys that mark the legacy nested schema.
_LEGACY_MARKERS = frozenset({
    "processor",
    "watcher",
})


def _resolve_path(base_dir: Path, value: str | Path) -> Path:
    """Resolve a path string against ``base_dir``.

    Absolute paths are returned as-is (after ``Path`` conversion). Relative
    paths are joined to ``base_dir``.
    """
    path = Path(value)
    if path.is_absolute():
        return path
    return base_dir / path


def _require_str(payload: dict[str, Any], key: str, *, context: str) -> str:
    if key not in payload or payload[key] is None:
        raise ValueError(f"{context}: missing required field '{key}'")
    value = payload[key]
    if not isinstance(value, str) or not value.strip():
        raise ValueError(
            f"{context}: '{key}' must be a non-empty string, got {value!r}"
        )
    return value.strip()


def _detect_config_format(payload: dict[str, Any]) -> str:
    """Return ``'simplified'`` or ``'legacy'``.

    Raises
    ------
    ValueError
        If the payload mixes both formats or matches neither.
    """
    has_simplified = bool(_SIMPLIFIED_MARKERS.intersection(payload))
    has_legacy = bool(_LEGACY_MARKERS.intersection(payload))

    if has_simplified and has_legacy:
        raise ValueError(
            "Config mixes simplified and legacy formats. Use either flat keys "
            "(input_folder, output_folder, corems_params, targeted, "
            "qc_compounds, sample_name_regex) or nested processor/watcher "
            "blocks — not both."
        )
    if has_simplified:
        return "simplified"
    if has_legacy:
        return "legacy"
    raise ValueError(
        "Unrecognized config format. Expected simplified keys "
        "(input_folder, output_folder, corems_params, ...) or legacy nested "
        "processor/watcher blocks."
    )


def _normalize_mode_from_targeted(targeted: Any) -> str:
    if not isinstance(targeted, bool):
        raise ValueError(
            f"simplified config: 'targeted' must be a boolean, got {targeted!r}"
        )
    return "targeted" if targeted else "untargeted"


def _normalize_mode_string(mode: Any, *, context: str) -> str:
    mode_str = str(mode).strip().lower()
    if mode_str not in {"targeted", "untargeted"}:
        raise ValueError(
            f"{context}: mode must be 'targeted' or 'untargeted', got '{mode_str}'"
        )
    return mode_str


def _optional_float(payload: dict[str, Any], key: str, default: float) -> float:
    if key not in payload or payload[key] is None:
        return default
    return float(payload[key])


def _optional_int(payload: dict[str, Any], key: str, default: int) -> int:
    if key not in payload or payload[key] is None:
        return default
    return int(payload[key])


def _optional_bool(payload: dict[str, Any], key: str, default: bool) -> bool:
    if key not in payload or payload[key] is None:
        return default
    return bool(payload[key])


def _normalize_discovery_mode(value: Any, *, context: str) -> str:
    """Return a validated discovery mode string."""
    if value is None:
        return "hybrid"
    mode = str(value).strip().lower()
    if mode not in DISCOVERY_MODES:
        allowed = ", ".join(sorted(DISCOVERY_MODES))
        raise ValueError(
            f"{context}: discovery_mode must be one of {{{allowed}}}, got {value!r}"
        )
    return mode


@dataclass(frozen=True)
class _NormalizedConfig:
    """Intermediate field bag shared by simplified and legacy loaders."""

    raw_dir: str | Path
    output_dir: str | Path
    params_path: str | Path
    mode: str
    standards_csv: str | Path | None
    sample_name_regex: str | None
    top_n: int
    mz_tolerance_ppm: float
    rt_tolerance: float
    min_area: float
    plot_eics: bool
    plot_tic: bool
    integrate_mass_features: bool
    cluster_mass_features: bool
    poll_interval_sec: float
    stability_wait_sec: float
    discovery_mode: str
    debounce_sec: float
    stale_in_progress_sec: int
    max_retries: int
    initial_backoff_sec: float
    backoff_multiplier: float


def _normalize_simplified(payload: dict[str, Any]) -> _NormalizedConfig:
    """Map flat simplified JSON into the shared intermediate config."""
    context = "simplified config"
    raw_dir = _require_str(payload, "input_folder", context=context)
    output_dir = _require_str(payload, "output_folder", context=context)
    params_path = _require_str(payload, "corems_params", context=context)
    sample_name_regex = _require_str(payload, "sample_name_regex", context=context)

    if "targeted" not in payload:
        raise ValueError(f"{context}: missing required field 'targeted'")
    mode = _normalize_mode_from_targeted(payload["targeted"])

    standards_csv: str | Path | None
    if mode == "targeted":
        standards_csv = _require_str(payload, "qc_compounds", context=context)
    else:
        # Optional in untargeted mode; ignored if present.
        standards_csv = payload.get("qc_compounds")
        if standards_csv is not None and (
            not isinstance(standards_csv, str) or not standards_csv.strip()
        ):
            raise ValueError(
                f"{context}: 'qc_compounds' must be a non-empty string when set"
            )

    top_n = _optional_int(payload, "top_n", 100)
    if top_n <= 0:
        raise ValueError(f"{context}: top_n must be > 0, got {top_n}")

    return _NormalizedConfig(
        raw_dir=raw_dir,
        output_dir=output_dir,
        params_path=params_path,
        mode=mode,
        standards_csv=standards_csv,
        sample_name_regex=sample_name_regex,
        top_n=top_n,
        mz_tolerance_ppm=_optional_float(payload, "mz_tolerance_ppm", 5.0),
        rt_tolerance=_optional_float(payload, "rt_tolerance", 0.5),
        min_area=_optional_float(payload, "min_area", 5e3),
        plot_eics=_optional_bool(payload, "plot_eics", False),
        plot_tic=_optional_bool(payload, "plot_tic", True),
        integrate_mass_features=_optional_bool(
            payload, "integrate_mass_features", False
        ),
        cluster_mass_features=_optional_bool(
            payload, "cluster_mass_features", False
        ),
        poll_interval_sec=_optional_float(payload, "poll_interval_sec", 10.0),
        stability_wait_sec=_optional_float(payload, "stability_wait_sec", 20.0),
        discovery_mode=_normalize_discovery_mode(
            payload.get("discovery_mode"), context=context
        ),
        debounce_sec=_optional_float(payload, "debounce_sec", 5.0),
        stale_in_progress_sec=_optional_int(payload, "stale_in_progress_sec", 3600),
        max_retries=_optional_int(payload, "max_retries", 3),
        initial_backoff_sec=_optional_float(payload, "initial_backoff_sec", 10.0),
        backoff_multiplier=_optional_float(payload, "backoff_multiplier", 2.0),
    )


def _normalize_legacy(payload: dict[str, Any]) -> _NormalizedConfig:
    """Map nested legacy JSON into the shared intermediate config."""
    processor = payload.get("processor") or {}
    watcher = payload.get("watcher") or {}
    synthesizer = payload.get("synthesizer") or {}
    search_space_payload = payload.get("search_space") or {}

    if not isinstance(processor, dict):
        raise ValueError("legacy config: 'processor' must be an object")
    if not isinstance(watcher, dict):
        raise ValueError("legacy config: 'watcher' must be an object")
    if not isinstance(synthesizer, dict):
        raise ValueError("legacy config: 'synthesizer' must be an object")
    if not isinstance(search_space_payload, dict):
        raise ValueError("legacy config: 'search_space' must be an object")

    if "output_dir" not in processor:
        raise ValueError("legacy config: processor.output_dir is required")
    if "params_path" not in processor:
        raise ValueError("legacy config: processor.params_path is required")
    if "raw_dir" not in watcher:
        raise ValueError("legacy config: watcher.raw_dir is required")

    mode = _normalize_mode_string(
        search_space_payload.get("mode", "targeted"),
        context="legacy config search_space",
    )
    top_n = int(search_space_payload.get("top_n", 100))
    if top_n <= 0:
        raise ValueError(
            f"legacy config: search_space.top_n must be > 0, got {top_n}"
        )

    standards_csv = processor.get("standards_csv")
    if mode == "targeted" and standards_csv is None:
        raise ValueError(
            "legacy config: processor.standards_csv is required when "
            "search_space.mode is 'targeted'"
        )

    sample_name_regex = watcher.get("sample_name_regex")
    if sample_name_regex is not None:
        sample_name_regex = str(sample_name_regex)

    return _NormalizedConfig(
        raw_dir=watcher["raw_dir"],
        output_dir=processor["output_dir"],
        params_path=processor["params_path"],
        mode=mode,
        standards_csv=standards_csv,
        sample_name_regex=sample_name_regex,
        top_n=top_n,
        mz_tolerance_ppm=float(processor.get("mz_tolerance_ppm", 5.0)),
        rt_tolerance=float(processor.get("rt_tolerance", 0.5)),
        min_area=float(processor.get("min_area", 5e3)),
        plot_eics=bool(processor.get("plot_eics", False)),
        plot_tic=bool(processor.get("plot_tic", True)),
        integrate_mass_features=bool(
            processor.get("integrate_mass_features", False)
        ),
        cluster_mass_features=bool(
            processor.get("cluster_mass_features", False)
        ),
        poll_interval_sec=float(watcher.get("poll_interval_sec", 10.0)),
        stability_wait_sec=float(watcher.get("stability_wait_sec", 20.0)),
        discovery_mode=_normalize_discovery_mode(
            watcher.get("discovery_mode"), context="legacy config watcher"
        ),
        debounce_sec=float(synthesizer.get("debounce_sec", 5.0)),
        stale_in_progress_sec=int(payload.get("stale_in_progress_sec", 3600)),
        max_retries=int(payload.get("max_retries", 3)),
        initial_backoff_sec=float(payload.get("initial_backoff_sec", 10.0)),
        backoff_multiplier=float(payload.get("backoff_multiplier", 2.0)),
    )


def _build_pipeline_config(
    normalized: _NormalizedConfig,
    base_dir: Path,
) -> PipelineConfig:
    """Build the runtime :class:`PipelineConfig` from normalized fields."""
    output_dir = _resolve_path(base_dir, normalized.output_dir)
    params_path = _resolve_path(base_dir, normalized.params_path)
    raw_dir = _resolve_path(base_dir, normalized.raw_dir)

    if normalized.mode == "untargeted":
        search_space_csv = output_dir / "untargeted_search_space.csv"
        if normalized.standards_csv is None:
            standards_csv_path = search_space_csv
        else:
            standards_csv_path = _resolve_path(base_dir, normalized.standards_csv)
    else:
        if normalized.standards_csv is None:
            raise ValueError(
                "standards CSV path is required when mode is 'targeted'"
            )
        standards_csv_path = _resolve_path(base_dir, normalized.standards_csv)
        search_space_csv = standards_csv_path

    return PipelineConfig(
        processor=ProcessorConfig(
            standards_csv=standards_csv_path,
            params_path=params_path,
            output_dir=output_dir,
            mz_tolerance_ppm=normalized.mz_tolerance_ppm,
            rt_tolerance=normalized.rt_tolerance,
            min_area=normalized.min_area,
            plot_eics=normalized.plot_eics,
            plot_tic=normalized.plot_tic,
            integrate_mass_features=normalized.integrate_mass_features,
            cluster_mass_features=normalized.cluster_mass_features,
        ),
        watcher=WatcherConfig(
            raw_dir=raw_dir,
            poll_interval_sec=normalized.poll_interval_sec,
            stability_wait_sec=normalized.stability_wait_sec,
            sample_name_regex=normalized.sample_name_regex,
            discovery_mode=normalized.discovery_mode,
        ),
        state=StateConfig(
            pipeline_manifest=output_dir / "pipeline_manifest.json",
            stale_in_progress_sec=normalized.stale_in_progress_sec,
        ),
        synthesizer=SynthesizerConfig(
            html_output=output_dir / "dashboard.html",
            output_dir=output_dir,
            debounce_sec=normalized.debounce_sec,
            mz_tolerance_ppm=normalized.mz_tolerance_ppm,
            rt_tolerance=normalized.rt_tolerance,
        ),
        search_space=SearchSpaceConfig(
            mode=normalized.mode,
            top_n=normalized.top_n,
            csv_path=search_space_csv,
        ),
        max_retries=normalized.max_retries,
        initial_backoff_sec=normalized.initial_backoff_sec,
        backoff_multiplier=normalized.backoff_multiplier,
    )


def load_pipeline_config(
    config_path: Path,
    base_dir: Path | None = None,
) -> PipelineConfig:
    """Load pipeline configuration from a JSON file.

    Accepts either the simplified flat schema or the legacy nested schema.
    Relative paths in the JSON are resolved against ``base_dir`` (default:
    the process current working directory).

    Parameters
    ----------
    config_path : Path
        Path to the JSON configuration file.
    base_dir : Path | None
        Directory used to resolve relative paths present in the JSON.
        Defaults to ``Path.cwd()``.

    Returns
    -------
    PipelineConfig
        Fully resolved pipeline configuration.
    """
    with config_path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)

    if not isinstance(payload, dict):
        raise ValueError("Config JSON root must be an object")

    root = Path.cwd() if base_dir is None else base_dir

    fmt = _detect_config_format(payload)
    if fmt == "simplified":
        normalized = _normalize_simplified(payload)
    else:
        normalized = _normalize_legacy(payload)

    return _build_pipeline_config(normalized, root)
