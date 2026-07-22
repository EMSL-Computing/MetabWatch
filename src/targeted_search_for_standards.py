"""
Single-file targeted LCMS search for QC standards.

This module processes one Thermo .raw file at a time, matches observed mass features
against a standards CSV, writes a CSV of matched observed features, and returns the
same results as a pandas DataFrame.
"""

import re
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

# Non-interactive backend required for CLI and GUI worker threads. The default
# macOS backend (MacOSX) can freeze or black-screen the Tk GUI when figures are
# created off the main thread after the first sample finishes plotting.
import matplotlib

matplotlib.use("Agg")
from matplotlib import pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from corems.encapsulation.input.parameter_from_json import load_and_set_toml_parameters_lcms
from corems.mass_spectra.factory.chromat_data import EIC_Data
from corems.mass_spectra.input.rawFileReader import ImportMassSpectraThermoMSFileReader


REQUIRED_STANDARDS_COLUMNS = {
    "compound_name",
    "ion_type",
    "mz",
    "retention_time",
    "polarity",
}


def _target_trace_col(compound_name: str) -> str:
    """Return deterministic trace column name for target-based EIC extraction."""
    safe_name = re.sub(r"[^0-9A-Za-z]+", "_", compound_name).strip("_")
    return f"target_{safe_name}" if safe_name else "target_compound"


def _normalize_acquisition_time(value: object) -> str | None:
    """Normalize acquisition-time values to UTC ISO8601.

    Parameters
    ----------
    value : object
        Candidate timestamp value from CoreMS metadata.

    Returns
    -------
    str | None
        ISO8601 UTC timestamp or None when parsing fails.
    """
    if value is None:
        return None

    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat()

    if isinstance(value, (int, float)):
        try:
            dt = datetime.fromtimestamp(float(value), tz=timezone.utc)
        except (OverflowError, ValueError):
            return None
        return dt.isoformat()

    parsed = pd.to_datetime(value, utc=True, errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed.to_pydatetime().astimezone(timezone.utc).isoformat()


def _build_eics_for_mz_list(
    lcms_obj: object,
    mz_values: list[float],
    mz_tolerance_ppm: float,
) -> None:
    """Build EICs directly from raw MS1 points for requested m/z values.

    This is used when integration is disabled and CoreMS has not populated
    `lcms_obj.eics`.
    """
    if not mz_values:
        return

    raw_data = getattr(lcms_obj, "_ms_unprocessed", {}).get(1)
    if raw_data is None or raw_data.empty:
        return

    scan_df_sub = (
        lcms_obj.scan_df[lcms_obj.scan_df["ms_level"] == 1][["scan", "scan_time"]]
        .copy()
        .reset_index(drop=True)
    )
    if scan_df_sub.empty:
        return

    raw_data_sorted = raw_data.sort_values(["mz", "scan"]).reset_index(drop=True)
    raw_data_mz = raw_data_sorted["mz"].to_numpy()

    for mz in sorted(set(float(x) for x in mz_values)):
        if mz in lcms_obj.eics:
            continue

        mz_tol = mz * mz_tolerance_ppm / 1e6
        mz_min = mz - mz_tol
        mz_max = mz + mz_tol

        left_idx = int(np.searchsorted(raw_data_mz, mz_min, side="left"))
        right_idx = int(np.searchsorted(raw_data_mz, mz_max, side="right"))
        raw_data_sub = raw_data_sorted.iloc[left_idx:right_idx].copy()

        if raw_data_sub.empty:
            intensity_by_scan = pd.DataFrame({"scan": [], "intensity": []})
        else:
            intensity_by_scan = (
                raw_data_sub.groupby(["scan"])["intensity"].sum().reset_index()
            )

        merged = scan_df_sub.merge(intensity_by_scan, on="scan", how="left")
        merged["intensity"] = merged["intensity"].fillna(0.0)

        lcms_obj.eics[mz] = EIC_Data(
            scans=merged["scan"].to_numpy(),
            time=merged["scan_time"].to_numpy(),
            eic=merged["intensity"].to_numpy(),
        )


def _extract_acquisition_time_iso(parser: object, lcms_obj: object) -> str:
    """Extract acquisition time from parser/LCMS metadata.

    Parameters
    ----------
    parser : object
        CoreMS parser object.
    lcms_obj : object
        CoreMS LCMS object.

    Returns
    -------
    str
        Acquisition timestamp in UTC ISO8601 format.

    Raises
    ------
    RuntimeError
        If no parseable acquisition/creation timestamp can be extracted.
    """
    candidate_names = (
        "get_creation_time",
        "creation_time",
        "created_at",
        "acquisition_time",
        "run_start_time",
        "start_time",
    )

    for container in (parser, lcms_obj):
        for name in candidate_names:
            if not hasattr(container, name):
                continue
            raw_value = getattr(container, name)
            if callable(raw_value):
                try:
                    raw_value = raw_value()
                except Exception:
                    continue
            normalized = _normalize_acquisition_time(raw_value)
            if normalized:
                return normalized

    raise RuntimeError(
        "Unable to extract acquisition time from CoreMS metadata for this sample"
    )


def _validate_inputs(
    raw_file: Path,
    standards_csv: Path,
    params_path: Path,
    output_dir: Path,
    mz_tolerance_ppm: float,
    rt_tolerance: float,
    min_area: float,
) -> None:
    """Validate input paths and numeric thresholds for a single run.

    Raises informative exceptions for missing files or invalid parameter values.
    """

    if not raw_file.exists() or not raw_file.is_file():
        raise FileNotFoundError(f"Raw file not found: {raw_file}")
    if raw_file.suffix.lower() != ".raw":
        raise ValueError(f"Expected a .raw file, got: {raw_file}")

    if not standards_csv.exists() or not standards_csv.is_file():
        raise FileNotFoundError(f"Standards CSV not found: {standards_csv}")

    if not params_path.exists() or not params_path.is_file():
        raise FileNotFoundError(f"CoreMS params TOML not found: {params_path}")

    if mz_tolerance_ppm <= 0:
        raise ValueError("mz_tolerance_ppm must be > 0")
    if rt_tolerance <= 0:
        raise ValueError("rt_tolerance must be > 0")
    if min_area < 0:
        raise ValueError("min_area must be >= 0")

    if not output_dir.exists():
        output_dir.mkdir(parents=True, exist_ok=True)


def _load_and_validate_standards(standards_csv: Path) -> pd.DataFrame:
    """Load standards CSV and validate required columns and types.

    Returns
    -------
    pd.DataFrame
        Validated standards table.
    """

    standards_df = pd.read_csv(standards_csv)
    missing_columns = sorted(REQUIRED_STANDARDS_COLUMNS - set(standards_df.columns))
    if missing_columns:
        raise ValueError(
            "Standards CSV is missing required columns: " + ", ".join(missing_columns)
        )

    standards_df["polarity"] = standards_df["polarity"].astype(str).str.strip().str.lower()
    standards_df["mz"] = pd.to_numeric(standards_df["mz"], errors="coerce")
    standards_df["retention_time"] = pd.to_numeric(
        standards_df["retention_time"], errors="coerce"
    )

    if standards_df["mz"].isna().any():
        raise ValueError("Standards CSV contains non-numeric values in mz")
    if standards_df["retention_time"].isna().any():
        raise ValueError("Standards CSV contains non-numeric values in retention_time")

    return standards_df


def process_raw_to_observed_features_df(
    raw_file: Path,
    standards_csv: Path,
    params_path: Path,
    output_dir: Path,
    mz_tolerance_ppm: float = 5.0,
    rt_tolerance: float = 0.5,
    min_area: float = 1e4,
    plot_eics: bool = True,
    plot_tic: bool = True,
    integrate_mass_features: bool = True,
    cluster_mass_features: bool = False,
    expected_polarity: str | None = None,
) -> pd.DataFrame:
    """Process a single `.raw` file and return matched observed features.

    The function writes per-sample artifacts (matches CSV, MS1 traces, EIC/TIC
    plots when requested) into `output_dir` and returns a pandas DataFrame of
    matched features.

    Parameters
    ----------
    raw_file : Path
        Path to the Thermo `.raw` file.
    standards_csv : Path
        Path to the standards CSV providing target compounds.
    params_path : Path
        Path to CoreMS TOML parameter file.
    output_dir : Path
        Directory where artifacts will be written.
    mz_tolerance_ppm : float
        m/z tolerance in ppm.
    rt_tolerance : float
        Retention time tolerance in minutes.
    min_area : float
        Minimum area threshold for matched features.
    plot_eics : bool
        Whether to generate EIC PDFs for matched features.
    plot_tic : bool
        Whether to generate a TIC PNG for the sample.
    integrate_mass_features : bool
        Whether to run CoreMS integration on detected mass features.
    cluster_mass_features : bool
        Whether to run CoreMS clustering on detected mass features.
    expected_polarity : str | None
        When set (from the pipeline manifest), CoreMS polarity must match.

    Returns
    -------
    pd.DataFrame
        DataFrame containing matched observed features. ``attrs['polarity']``
        holds the normalized CoreMS polarity string.
    """
    _validate_inputs(
        raw_file=raw_file,
        standards_csv=standards_csv,
        params_path=params_path,
        output_dir=output_dir,
        mz_tolerance_ppm=mz_tolerance_ppm,
        rt_tolerance=rt_tolerance,
        min_area=min_area,
    )

    raw_tag = raw_file.stem
    output_csv = output_dir / f"{raw_tag}_targeted_matches.csv"
    trace_csv = output_dir / f"{raw_tag}_ms1_traces.csv"
    plot_pdf = output_dir / f"{raw_tag}_eics.pdf"
    tic_png = output_dir / f"{raw_tag}_tic.png"

    standards_df = _load_and_validate_standards(standards_csv)

    print(f"Loading raw file: {raw_file}")
    try:
        parser = ImportMassSpectraThermoMSFileReader(raw_file)
        lcms_obj = parser.get_lcms_obj(spectra="ms1")
    except Exception as exc:
        raise RuntimeError(f"Failed to parse raw file {raw_file}: {exc}") from exc

    if lcms_obj is None:
        raise RuntimeError(f"Failed to instantiate LCMS object for {raw_file}")

    acquisition_time = _extract_acquisition_time_iso(parser=parser, lcms_obj=lcms_obj)

    try:
        load_and_set_toml_parameters_lcms(lcms_obj, params_path)
    except Exception as exc:
        raise RuntimeError(
            f"Failed to load CoreMS parameter file {params_path}: {exc}"
        ) from exc

    raw_polarity = str(lcms_obj.polarity).strip().lower()
    if expected_polarity is not None:
        expected = str(expected_polarity).strip().lower()
        if raw_polarity != expected:
            raise ValueError(
                f"Polarity mismatch: file {raw_file.name} is '{raw_polarity}' "
                f"but this run is locked to '{expected}'. "
                "MetabWatch does not allow mixed polarities in one input folder / run."
            )
    target_df = standards_df[standards_df["polarity"] == raw_polarity].copy()
    if target_df.empty:
        raise ValueError(
            f"No standards found for raw file polarity '{raw_polarity}'. "
            "Confirm the standards CSV polarity column values."
        )

    target_search_dict = {
        "target_mz_list": target_df["mz"].tolist(),
        "target_rt_list": target_df["retention_time"].tolist(),
        "mz_tolerance_ppm": mz_tolerance_ppm,
        "rt_tolerance": rt_tolerance,
        "type": "qc standard",
    }

    lcms_obj.find_mass_features(targeted_search=True, target_search_dict=target_search_dict)
    if integrate_mass_features:
        # Keep the full feature set: do not drop failed/duplicate peaks so
        # intensity-based match selection stays stable vs pre-integration runs.
        lcms_obj.integrate_mass_features(drop_if_fail=False, drop_duplicates=False)
    lcms_obj.add_associated_ms1()
    if cluster_mass_features:
        lcms_obj.cluster_mass_features()
        # Re-integrate surviving parents so area/EIC bounds match the post-cluster set.
        if integrate_mass_features:
            lcms_obj.integrate_mass_features(drop_if_fail=False, drop_duplicates=False)

    mf_df = lcms_obj.mass_features_to_df(drop_na_cols=True)
    required_mf_columns = {"mz", "scan_time"}
    missing_mf_columns = sorted(required_mf_columns - set(mf_df.columns))
    if missing_mf_columns:
        raise RuntimeError(
            "CoreMS mass features DataFrame missing required columns: "
            + ", ".join(missing_mf_columns)
        )

    has_area = "area" in mf_df.columns
    if min_area > 0 and not has_area:
        print(
            "[warning] 'area' is unavailable in CoreMS mass features; "
            "skipping min_area filtering"
        )

    file_results = []
    for idx, mf_row in mf_df.iterrows():
        observed_mz = mf_row.get("mz")
        observed_rt = mf_row.get("scan_time")

        mz_ppm_diff = abs((target_df["mz"] - observed_mz) / target_df["mz"] * 1e6)
        rt_diff = abs(target_df["retention_time"] - observed_rt)

        matches = target_df[
            (mz_ppm_diff <= mz_tolerance_ppm) & (rt_diff <= rt_tolerance)
        ]

        for _, match_row in matches.iterrows():
            result = {
                "mf_id": idx,
                "filename": raw_file.name,
                "compound_name": match_row["compound_name"],
                "ion_type": match_row["ion_type"],
                "polarity": match_row["polarity"],
                "target_mz": match_row["mz"],
                "target_rt": match_row["retention_time"],
                "observed_mz": observed_mz,
                "observed_rt": observed_rt,
                "mz_error_ppm": (observed_mz - match_row["mz"]) / match_row["mz"] * 1e6,
                "rt_error": observed_rt - match_row["retention_time"],
            }
            for col in mf_df.columns:
                if col not in result:
                    result[col] = mf_row[col]
            file_results.append(result)

    results_df = pd.DataFrame(file_results)

    if min_area > 0 and not results_df.empty and has_area:
        results_df = results_df[results_df["area"] >= min_area].copy()

    # Keep one hit per compound by selecting the highest-intensity matched feature.
    if not results_df.empty:
        if "intensity" not in results_df.columns:
            raise RuntimeError(
                "Expected 'intensity' in matched results for duplicate resolution"
            )
        results_df = (
            results_df.sort_values("intensity", ascending=False)
            .drop_duplicates(subset=["compound_name"], keep="first")
            .reset_index(drop=True)
        )

    results_df["acquisition_time"] = acquisition_time
    results_df.attrs["acquisition_time"] = acquisition_time
    results_df.attrs["polarity"] = raw_polarity

    if plot_eics and not results_df.empty:
        plot_pdf.parent.mkdir(parents=True, exist_ok=True)

        mf_compounds = (
            results_df.groupby("mf_id")["compound_name"]
            .apply(lambda s: sorted(set(s.astype(str).tolist())))
            .to_dict()
        )

        with PdfPages(plot_pdf) as pdf:
            for mf_id in sorted(mf_compounds):
                if mf_id not in lcms_obj.mass_features:
                    continue
                fig = lcms_obj.mass_features[mf_id].plot()
                compounds = ", ".join(mf_compounds[mf_id])
                fig.suptitle(
                    f"Mass Feature ID: {mf_id} | Compound(s): {compounds}",
                    fontsize=9,
                    y=0.98,
                )
                fig.tight_layout()
                pdf.savefig(fig)
                fig.clf()

        print(f"EIC plots saved to: {plot_pdf}")

    if plot_tic:
        tic_png.parent.mkdir(parents=True, exist_ok=True)

        tic_df = lcms_obj.scan_df[lcms_obj.scan_df["ms_level"] == 1]
        fig, ax = plt.subplots(figsize=(10, 4))
        ax.plot(tic_df["scan_time"], tic_df["tic"], linewidth=0.8)
        ax.set_xlabel("Retention Time (min)")
        ax.set_ylabel("TIC")
        ax.set_title(f"TIC | Sample: {raw_file.name} | Polarity: {raw_polarity}")
        fig.tight_layout()
        fig.savefig(tic_png, dpi=200)
        plt.close(fig)

        print(f"TIC plot saved to: {tic_png}")

    trace_csv.parent.mkdir(parents=True, exist_ok=True)

    ms1_df = (
        lcms_obj.scan_df[lcms_obj.scan_df["ms_level"] == 1][["scan", "scan_time", "tic"]]
        .copy()
        .rename(columns={"scan_time": "time"})
        .sort_values("scan")
        .reset_index(drop=True)
    )

    # Integration-disabled mode does not populate `lcms_obj.eics`; build target and
    # matched-feature EICs directly so dashboard traces are still available.
    if not getattr(lcms_obj, "eics", None):
        mz_values_for_eics = target_df["mz"].dropna().astype(float).tolist()
        if not results_df.empty and "observed_mz" in results_df.columns:
            mz_values_for_eics.extend(
                results_df["observed_mz"].dropna().astype(float).tolist()
            )
        _build_eics_for_mz_list(
            lcms_obj=lcms_obj,
            mz_values=mz_values_for_eics,
            mz_tolerance_ppm=mz_tolerance_ppm,
        )

    if not results_df.empty:
        final_hits = (
            results_df[["mf_id", "compound_name"]]
            .drop_duplicates(subset=["mf_id"], keep="first")
            .sort_values("mf_id")
        )

        for _, row in final_hits.iterrows():
            mf_id = int(row["mf_id"])
            compound_name = str(row["compound_name"])
            if mf_id not in lcms_obj.mass_features:
                continue

            safe_name = re.sub(r"[^0-9A-Za-z]+", "_", compound_name).strip("_")
            col_name = f"mf_{mf_id}_{safe_name}" if safe_name else f"mf_{mf_id}"

            eic_data = lcms_obj.mass_features[mf_id]._eic_data
            if eic_data is None:
                mf_mz = float(lcms_obj.mass_features[mf_id].mz)
                mz_tol = mf_mz * mz_tolerance_ppm / 1e6
                key = lcms_obj.get_eic_mz_for_mass_feature(mf_mz, tolerance=mz_tol)
                if key is not None and key in lcms_obj.eics:
                    eic_data = lcms_obj.eics[key]
            if eic_data is None or not hasattr(eic_data, "scans") or not hasattr(eic_data, "eic"):
                continue
            if eic_data.scans is None or eic_data.eic is None:
                continue
            eic_df = pd.DataFrame({
                "scan": eic_data.scans,
                col_name: eic_data.eic,
            })
            ms1_df = ms1_df.merge(eic_df, on="scan", how="left")

    # Always export target-based EIC traces for each expected compound so
    # non-detected compounds still have a real CoreMS-extracted chromatogram.
    target_export = (
        target_df[["compound_name", "mz"]]
        .dropna(subset=["compound_name", "mz"])
        .drop_duplicates(subset=["compound_name"], keep="first")
    )
    eic_keys = list(lcms_obj.eics.keys()) if getattr(lcms_obj, "eics", None) else []
    for _, row in target_export.iterrows():
        compound_name = str(row["compound_name"])
        target_mz = float(row["mz"])
        col_name = _target_trace_col(compound_name)

        key = None
        abs_tolerance = target_mz * mz_tolerance_ppm / 1e6
        try:
            key = lcms_obj.get_eic_mz_for_mass_feature(target_mz, tolerance=abs_tolerance)
        except Exception:
            key = None

        if key is None and eic_keys:
            key = min(eic_keys, key=lambda candidate: abs(float(candidate) - target_mz))

        if key is None or key not in lcms_obj.eics:
            continue

        eic_data = lcms_obj.eics[key]
        if eic_data is None or not hasattr(eic_data, "scans") or not hasattr(eic_data, "eic"):
            continue
        if eic_data.scans is None or eic_data.eic is None:
            continue
        eic_df = pd.DataFrame({
            "scan": eic_data.scans,
            col_name: eic_data.eic,
        })
        ms1_df = ms1_df.merge(eic_df, on="scan", how="left")

    ms1_df = ms1_df.drop(columns=["scan"])
    ms1_df["acquisition_time"] = acquisition_time
    ms1_df.to_csv(trace_csv, index=False)
    print(f"MS1 EIC/TIC trace table saved to: {trace_csv}")

    results_df.to_csv(output_csv, index=False)

    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Raw file processed: {raw_file.name}")
    print(f"Polarity: {raw_polarity}")
    print(f"Standards considered: {len(target_df)}")
    print(f"Matched features: {len(results_df)}")
    print(f"Output CSV: {output_csv}")

    return results_df


if __name__ == "__main__":
    # Example usage with hardcoded paths and parameters for local testing.
    raw_file = Path(
        "data/raw_positive/QC_Metab_25-02_Monet_HILIC_Pos-01B_26Dec25_Olympic_WBEH-9262_RR.raw"
    )
    standards_csv = Path("data/qc_search_space/hilic_qc_search.csv")
    params_path = Path("data/corems_params/monet_hilic_corems_lcms_params.toml")
    output_dir = Path("data/results_hilic_pos")
    output_dir.mkdir(parents=True, exist_ok=True)

    mz_tolerance_ppm = 5.0
    rt_tolerance = 0.5
    min_area = 5e3

    # Keep plot toggles configurable for local runs.
    plot_eics = True
    plot_tic = True

    process_raw_to_observed_features_df(
        raw_file=raw_file,
        standards_csv=standards_csv,
        params_path=params_path,
        output_dir=output_dir,
        mz_tolerance_ppm=mz_tolerance_ppm,
        rt_tolerance=rt_tolerance,
        min_area=min_area,
        plot_eics=plot_eics,
        plot_tic=plot_tic,
    )
