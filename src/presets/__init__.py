"""Built-in PNNL Standard RP / HILIC metabolomics pipeline presets.

Scientific assets (CoreMS TOML + QC compound CSVs) ship as package data under
``metabwatch.presets.<method_key>/``. Packaged ``corems.toml`` files list only
LC-MS keys that differ from CoreMS 4.0.1 defaults and that MetabWatch uses
(peak picking, EIC integration, clustering). Call :func:`build_pipeline_config`
for standard method × search modes; the CLI and GUI both use this API.

General ``*_metab_pnnl`` keys use a wider RT window for any LC/MS system.
``*_metab_olympic_eclipse01`` keys use the same QC RTs with a tighter window
for Olympic LC / Eclipse 01.
"""

from __future__ import annotations

from pathlib import Path
from typing import TypedDict

from metabwatch.config import (
    PipelineConfig,
    _NormalizedConfig,
    _build_pipeline_config,
    _normalize_optional_polarity,
    _normalize_project_id,
)


class PresetSpec(TypedDict):
    display_name: str
    mz_tolerance_ppm: float
    rt_tolerance: float
    min_area: float


PRESET_SPECS: dict[str, PresetSpec] = {
    "hilic_metab_pnnl": {
        "display_name": "PNNL Standard HILIC Metabolomics Method",
        "mz_tolerance_ppm": 5.0,
        "rt_tolerance": 0.8,
        "min_area": 1000.0,
    },
    "hilic_metab_olympic_eclipse01": {
        "display_name": (
            "PNNL Standard HILIC Metabolomics Method — Olympic LC / Eclipse 01"
        ),
        "mz_tolerance_ppm": 5.0,
        "rt_tolerance": 0.6,
        "min_area": 1000.0,
    },
    "rp_metab_pnnl": {
        "display_name": "PNNL Standard RP Metabolomics Method",
        "mz_tolerance_ppm": 5.0,
        "rt_tolerance": 0.4,
        "min_area": 20000.0,
    },
    "rp_metab_olympic_eclipse01": {
        "display_name": (
            "PNNL Standard RP Metabolomics Method — Olympic LC / Eclipse 01"
        ),
        "mz_tolerance_ppm": 5.0,
        "rt_tolerance": 0.2,
        "min_area": 20000.0,
    },
}

METHOD_KEYS: tuple[str, ...] = tuple(PRESET_SPECS)
_METHODS = frozenset(METHOD_KEYS)
_SEARCHES = frozenset({"targeted", "untargeted"})

_SAMPLE_REGEX = {
    "targeted": r"QC_Metab_(.+)",
    "untargeted": r"(?i)Pool",
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
    project_id: str = "",
) -> PipelineConfig:
    """Build a :class:`PipelineConfig` for a standard method × search mode.

    Parameters
    ----------
    method
        Chromatography / LC-MS preset key (see ``METHOD_KEYS``).
    search
        Search mode: ``"targeted"`` or ``"untargeted"``.
    input_folder
        Directory of Thermo ``.raw`` files.
    output_folder
        Results directory (dashboard, manifest, exports).
    polarity
        Optional run polarity (``positive`` / ``negative``). ``None`` keeps
        locking from the first successfully processed sample.
    project_id
        Optional case-insensitive filename-stem substring (batch / project).
        Empty means no extra filter; the preset sample-name regex still applies.

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

    spec = PRESET_SPECS[method_key]
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
        mz_tolerance_ppm=spec["mz_tolerance_ppm"],
        rt_tolerance=spec["rt_tolerance"],
        min_area=spec["min_area"],
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
        project_id=_normalize_project_id(project_id),
    )
    # Absolute paths already; base_dir is only used for any remaining relatives.
    return _build_pipeline_config(normalized, base_dir=Path.cwd())
