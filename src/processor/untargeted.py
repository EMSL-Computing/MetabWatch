from __future__ import annotations

"""Build an untargeted search space from a single raw file.

Runs CoreMS untargeted peak picking + integration on one Thermo `.raw` file,
applies in-place peak-metric filtering to drop poorly-integrated features,
clusters duplicate mass features in mz/rt space, ranks the survivors by
integrated area (descending), keeps the top-N, and writes a standards-shaped
CSV that the rest of the pipeline can consume just like a hand-curated
standards file.

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
    expected_polarity: str | None = None,
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
    expected_polarity : str | None
        When set (from the pipeline manifest), CoreMS polarity must match.

    Returns
    -------
    pd.DataFrame
        The DataFrame written to disk plus the original `area` column for
        diagnostics. The CSV on disk contains only `SEARCH_SPACE_COLUMNS`.
        ``attrs['polarity']`` holds the normalized CoreMS polarity string.
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
    if expected_polarity is not None:
        expected = str(expected_polarity).strip().lower()
        if polarity != expected:
            raise ValueError(
                f"Polarity mismatch: file {raw_file.name} is '{polarity}' "
                f"but this run is locked to '{expected}'. "
                "MetabWatch does not allow mixed polarities in one input folder / run."
            )

    # Override CoreMS settings on the lcms_obj for this run only. We don't
    # mutate the shared TOML — the targeted pipeline reads the same file and
    # has its own preferences. Specifically:
    #   * remove_mass_features_by_peak_metrics: enable in-place pruning of
    #     poorly-integrated features after add_peak_metrics(), using the
    #     mass_feature_attribute_filter_dict thresholds from the TOML.
    #   * mass_feature_cluster_mz_tolerance_rel: bump to 1.5e-5 (15 ppm) so
    #     the post-integration clustering pass collapses the residual ~5-13
    #     ppm duplicates that survive the default 5 ppm window.
    lcms_obj.parameters.lc_ms.mass_feature_cluster_mz_tolerance_rel = 1.5e-5

    lcms_obj.find_mass_features()
    # Keep the full feature set: do not drop failed/duplicate peaks during integration.
    lcms_obj.integrate_mass_features(drop_if_fail=False, drop_duplicates=False)
    lcms_obj.cluster_mass_features(drop_children=True, sort_by="persistence")
    # Re-integrate surviving parents so area/EIC bounds match the post-cluster set.
    lcms_obj.integrate_mass_features(drop_if_fail=False, drop_duplicates=False)

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
            f"CoreMS produced 0 untargeted mass features for {raw_file.name} "
            "(after integration / quality filter / clustering)"
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
    diagnostic_df.attrs["polarity"] = polarity
    return diagnostic_df
