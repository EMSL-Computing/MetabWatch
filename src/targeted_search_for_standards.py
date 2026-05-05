"""
Single-file targeted LCMS search for QC standards.

This module processes one Thermo .raw file at a time, matches observed mass features
against a standards CSV, writes a CSV of matched observed features, and returns the
same results as a pandas DataFrame.
"""

import argparse
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from matplotlib import pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from corems.encapsulation.input.parameter_from_json import load_and_set_toml_parameters_lcms
from corems.mass_spectra.input.rawFileReader import ImportMassSpectraThermoMSFileReader


REQUIRED_STANDARDS_COLUMNS = {
    "compound_name",
    "ion_type",
    "mz",
    "retention_time",
    "polarity",
}


def _validate_inputs(
    raw_file: Path,
    standards_csv: Path,
    params_path: Path,
    output_csv: Path,
    mz_tolerance_ppm: float,
    rt_tolerance: float,
    min_area: float,
) -> None:
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

    output_parent = output_csv.parent
    if output_parent and not output_parent.exists():
        output_parent.mkdir(parents=True, exist_ok=True)


def _load_and_validate_standards(standards_csv: Path) -> pd.DataFrame:
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
    output_csv: Path,
    mz_tolerance_ppm: float = 5.0,
    rt_tolerance: float = 0.5,
    min_area: float = 1e4,
    plot_eics: bool = False,
    plot_pdf: Path | None = None,
    plot_tic: bool = False,
    tic_png: Path | None = None,
) -> pd.DataFrame:
    """
    Process one .raw file and return matched observed features as a DataFrame.

    A CSV is always written to output_csv.
    """
    _validate_inputs(
        raw_file=raw_file,
        standards_csv=standards_csv,
        params_path=params_path,
        output_csv=output_csv,
        mz_tolerance_ppm=mz_tolerance_ppm,
        rt_tolerance=rt_tolerance,
        min_area=min_area,
    )

    standards_df = _load_and_validate_standards(standards_csv)

    print(f"Loading raw file: {raw_file}")
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

    raw_polarity = str(lcms_obj.polarity).strip().lower()
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
    lcms_obj.integrate_mass_features()
    lcms_obj.add_associated_ms1()
    lcms_obj.cluster_mass_features()

    mf_df = lcms_obj.mass_features_to_df(drop_na_cols=True)
    required_mf_columns = {"mz", "scan_time"}
    missing_mf_columns = sorted(required_mf_columns - set(mf_df.columns))
    if missing_mf_columns:
        raise RuntimeError(
            "CoreMS mass features DataFrame missing required columns: "
            + ", ".join(missing_mf_columns)
        )

    if min_area > 0 and "area" not in mf_df.columns:
        raise RuntimeError(
            "CoreMS mass features DataFrame does not contain 'area', "
            "but min_area filtering was requested"
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

    if min_area > 0 and not results_df.empty:
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

    if plot_eics and not results_df.empty:
        if plot_pdf is None:
            plot_pdf = output_csv.with_suffix(".eics.pdf")
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
        if tic_png is None:
            tic_png = output_csv.with_suffix(".tic.png")
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


def main() -> None:
    load_dotenv()

    parser = argparse.ArgumentParser(
        description=(
            "Process one .raw file against standards and export matched observed features."
        )
    )
    parser.add_argument("--raw_file", type=Path, required=True, help="Path to a .raw file")
    parser.add_argument(
        "--standards_csv",
        type=Path,
        required=True,
        help="Path to standards CSV with required columns",
    )
    parser.add_argument(
        "--params_path",
        type=Path,
        required=True,
        help="Path to CoreMS TOML parameter file",
    )
    parser.add_argument(
        "--output_csv", type=Path, required=True, help="Path to output CSV file"
    )
    parser.add_argument(
        "--mz_tolerance_ppm", type=float, default=5.0, help="m/z tolerance in ppm"
    )
    parser.add_argument(
        "--rt_tolerance", type=float, default=0.5, help="RT tolerance in minutes"
    )
    parser.add_argument(
        "--min_area", type=float, default=1e4, help="Minimum peak area threshold"
    )
    parser.add_argument(
        "--plot_eics",
        action="store_true",
        help="Generate EIC plots for filtered remaining mass features",
    )
    parser.add_argument(
        "--plot_pdf",
        type=Path,
        default=None,
        help="Optional output PDF path for EIC plots (default: output_csv with .eics.pdf)",
    )
    parser.add_argument(
        "--plot_tic",
        action="store_true",
        help="Generate TIC plot for the processed sample",
    )
    parser.add_argument(
        "--tic_png",
        type=Path,
        default=None,
        help="Optional output PNG path for TIC plot (default: output_csv with .tic.png)",
    )

    args = parser.parse_args()

    process_raw_to_observed_features_df(
        raw_file=args.raw_file,
        standards_csv=args.standards_csv,
        params_path=args.params_path,
        output_csv=args.output_csv,
        mz_tolerance_ppm=args.mz_tolerance_ppm,
        rt_tolerance=args.rt_tolerance,
        min_area=args.min_area,
        plot_eics=args.plot_eics,
        plot_pdf=args.plot_pdf,
        plot_tic=args.plot_tic,
        tic_png=args.tic_png,
    )


if __name__ == "__main__":
    main()
