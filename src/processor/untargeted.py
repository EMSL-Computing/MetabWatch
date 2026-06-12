from __future__ import annotations

"""Build an untargeted search space from a single raw file.

Runs CoreMS untargeted peak picking + integration on one Thermo `.raw` file,
ranks the resulting mass features by integrated area (descending), keeps the
top-N, and writes a standards-shaped CSV that the rest of the pipeline can
consume just like a hand-curated standards file.

This module has a single responsibility: write
`<output_dir>/untargeted_search_space.csv`. It does NOT write per-sample
artifacts; those are produced by the regular per-sample processing pass.
"""

from pathlib import Path

import pandas as pd
from corems.encapsulation.input.parameter_from_json import load_and_set_toml_parameters_lcms
from corems.mass_spectra.input.rawFileReader import ImportMassSpectraThermoMSFileReader


SEARCH_SPACE_COLUMNS = [
    "compound_name",
    "ion_type",
    "mz",
    "retention_time",
    "polarity",
]


def _validate_inputs(
    raw_file: Path,
    params_path: Path,
    output_csv: Path,
    top_n: int,
    mz_tolerance_ppm: float,
) -> None:
    """Validate inputs for the untargeted search-space build."""
    if not raw_file.exists() or not raw_file.is_file():
        raise FileNotFoundError(f"Raw file not found: {raw_file}")
    if raw_file.suffix.lower() != ".raw":
        raise ValueError(f"Expected a .raw file, got: {raw_file}")
    if not params_path.exists() or not params_path.is_file():
        raise FileNotFoundError(f"CoreMS params TOML not found: {params_path}")
    if top_n <= 0:
        raise ValueError("top_n must be > 0")
    if mz_tolerance_ppm <= 0:
        raise ValueError("mz_tolerance_ppm must be > 0")
    output_csv.parent.mkdir(parents=True, exist_ok=True)


def build_untargeted_search_space(
    raw_file: Path,
    params_path: Path,
    output_csv: Path,
    top_n: int,
    mz_tolerance_ppm: float,
) -> pd.DataFrame:
    """Run untargeted peak picking on `raw_file` and write a top-N search-space CSV.

    Parameters
    ----------
    raw_file : Path
        Thermo `.raw` file used to seed the search space.
    params_path : Path
        Path to the CoreMS TOML parameter file.
    output_csv : Path
        Destination for the standards-shaped CSV
        (typically `<output_dir>/untargeted_search_space.csv`).
    top_n : int
        Maximum number of peaks to keep, ranked by integrated area descending.
    mz_tolerance_ppm : float
        Reserved for future use; validated > 0 for consistency with the
        targeted pipeline. Not currently consumed by CoreMS in the untargeted
        path, but accepted to keep the signature symmetric with downstream code.

    Returns
    -------
    pd.DataFrame
        The DataFrame written to disk plus the original `area` column for
        diagnostics. The CSV on disk contains only `SEARCH_SPACE_COLUMNS`.
    """
    _validate_inputs(
        raw_file=raw_file,
        params_path=params_path,
        output_csv=output_csv,
        top_n=top_n,
        mz_tolerance_ppm=mz_tolerance_ppm,
    )

    print(f"[untargeted] parsing raw file: {raw_file}")
    try:
        parser = ImportMassSpectraThermoMSFileReader(raw_file)
        lcms_obj = parser.get_lcms_obj(spectra="ms1")
    except Exception as exc:
        raise RuntimeError(f"Failed to parse raw file {raw_file}: {exc}") from exc

    if lcms_obj is None:
        raise RuntimeError(f"Failed to instantiate LCMS object for {raw_file}")

    try:
        load_and_set_toml_parameters_lcms(lcms_obj, params_path)
    except Exception as exc:
        raise RuntimeError(
            f"Failed to load CoreMS parameter file {params_path}: {exc}"
        ) from exc

    polarity = str(lcms_obj.polarity).strip().lower()

    lcms_obj.find_mass_features()
    lcms_obj.integrate_mass_features()

    mf_df = lcms_obj.mass_features_to_df(drop_na_cols=True)
    required = {"mz", "scan_time", "area"}
    missing = sorted(required - set(mf_df.columns))
    if missing:
        raise RuntimeError(
            "CoreMS untargeted features missing required columns: "
            + ", ".join(missing)
            + " (integration may have failed)"
        )

    if mf_df.empty:
        raise RuntimeError(
            f"CoreMS produced 0 untargeted mass features for {raw_file.name}"
        )

    ranked = mf_df.sort_values("area", ascending=False).reset_index(drop=True)
    kept = ranked.head(top_n).copy()
    if len(kept) < top_n:
        print(
            f"[warning] only {len(kept)} peaks found; requested top_n={top_n}"
        )

    name_width = max(3, len(str(top_n)))
    kept["compound_name"] = [
        f"feature_{i:0{name_width}d}" for i in range(1, len(kept) + 1)
    ]
    kept["ion_type"] = "unknown"
    kept["polarity"] = polarity
    kept = kept.rename(columns={"scan_time": "retention_time"})

    diagnostic_df = kept[SEARCH_SPACE_COLUMNS + ["area"]].copy()
    tmp_path = output_csv.with_suffix(output_csv.suffix + ".tmp")
    diagnostic_df.drop(columns=["area"]).to_csv(tmp_path, index=False)
    tmp_path.replace(output_csv)
    print(
        f"[untargeted] wrote {output_csv} with {len(diagnostic_df)} features "
        f"(polarity={polarity})"
    )
    return diagnostic_df
