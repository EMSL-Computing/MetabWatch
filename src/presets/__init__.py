"""Built-in PNNL Standard RP / HILIC metabolomics pipeline presets.

Scientific assets (CoreMS TOML + QC compound CSVs) ship as package data under
``metabwatch.presets.{hilic_metab_pnnl,rp_metab_pnnl}/``. Call
:func:`build_pipeline_config` for the four common modes; the CLI and GUI both
use this API.
"""

from __future__ import annotations

from pathlib import Path

from metabwatch.config import (
    PipelineConfig,
    _NormalizedConfig,
    _build_pipeline_config,
    _normalize_optional_polarity,
)

_METHODS = frozenset({"rp_metab_pnnl", "hilic_metab_pnnl"})
_SEARCHES = frozenset({"targeted", "untargeted"})

_THRESHOLDS: dict[str, dict[str, float]] = {
    "hilic_metab_pnnl": {
        "mz_tolerance_ppm": 5.0,
        "rt_tolerance": 0.8,
        "min_area": 1000.0,
    },
    "rp_metab_pnnl": {
        "mz_tolerance_ppm": 5.0,
        "rt_tolerance": 0.4,
        "min_area": 20000.0,
    },
}

_SAMPLE_REGEX = {
    "targeted": r"QC_Metab_(.+)",
    "untargeted": r"(?i)Pooled",
}


def _asset_path(method: str, filename: str) -> Path:
    """Return the on-disk path to a packaged preset asset."""
    base = Path(__file__).resolve().parent / method / filename
    if not base.is_file():
        raise FileNotFoundError(f"Missing preset asset: {base}")
    return base


def build_pipeline_config(
    method: str,
    search: str,
    input_folder: Path | str,
    output_folder: Path | str,
    polarity: str | None = None,
) -> PipelineConfig:
    """Build a :class:`PipelineConfig` for a standard method × search mode.

    Parameters
    ----------
    method
        Chromatography method: ``"rp_metab_pnnl"`` or ``"hilic_metab_pnnl"``.
    search
        Search mode: ``"targeted"`` or ``"untargeted"``.
    input_folder
        Directory of Thermo ``.raw`` files.
    output_folder
        Results directory (dashboard, manifest, exports).
    polarity
        Optional run polarity (``positive`` / ``negative``). ``None`` keeps
        locking from the first successfully processed sample.

    Returns
    -------
    PipelineConfig
        Fully resolved runtime configuration.

    Raises
    ------
    ValueError
        If ``method``, ``search``, or ``polarity`` is not recognized.
    FileNotFoundError
        If a packaged CoreMS or QC asset is missing.
    """
    method_key = str(method).strip().lower()
    search_key = str(search).strip().lower()
    if method_key not in _METHODS:
        raise ValueError(
            f"Unknown method {method!r}; expected one of {sorted(_METHODS)}"
        )
    if search_key not in _SEARCHES:
        raise ValueError(
            f"Unknown search {search!r}; expected one of {sorted(_SEARCHES)}"
        )

    thr = _THRESHOLDS[method_key]
    params = _asset_path(method_key, "corems.toml")
    standards = (
        _asset_path(method_key, "qc_compounds.csv")
        if search_key == "targeted"
        else None
    )

    # Resolve user paths so cwd does not affect relative inputs.
    raw_dir = Path(input_folder).expanduser().resolve()
    output_dir = Path(output_folder).expanduser().resolve()

    normalized = _NormalizedConfig(
        raw_dir=raw_dir,
        output_dir=output_dir,
        params_path=params,
        mode=search_key,
        standards_csv=standards,
        sample_name_regex=_SAMPLE_REGEX[search_key],
        top_n=100,
        mz_tolerance_ppm=thr["mz_tolerance_ppm"],
        rt_tolerance=thr["rt_tolerance"],
        min_area=thr["min_area"],
        plot_eics=False,
        plot_tic=True,
        integrate_mass_features=True,
        cluster_mass_features=False,
        poll_interval_sec=10.0,
        stability_wait_sec=20.0,
        discovery_mode="hybrid",
        debounce_sec=5.0,
        stale_in_progress_sec=3600,
        max_retries=3,
        initial_backoff_sec=10.0,
        backoff_multiplier=2.0,
        polarity=_normalize_optional_polarity(polarity, context="preset"),
    )
    # Absolute paths already; base_dir is only used for any remaining relatives.
    return _build_pipeline_config(normalized, base_dir=Path.cwd())
