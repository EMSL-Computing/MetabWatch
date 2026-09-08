"""Per-sample match/TIC/trace files live under matches/ and traces/, not the results root."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from metabwatch.output.layout import (
    MATCHES_DIRNAME,
    TRACES_DIRNAME,
    matches_dir,
    relocate_legacy_outputs,
    relocate_legacy_traces,
    resolve_trace_csv,
    sample_eics_pdf,
    sample_match_csv,
    sample_tic_png,
    sample_trace_csv,
    traces_dir,
)
from metabwatch.synthesis.synthesizer import HTMLSynthesizer


def test_preferred_paths_are_under_matches_and_traces(tmp_path: Path) -> None:
    output_dir = tmp_path / "results"
    stem = "QC_Metab_pos_01"
    assert traces_dir(output_dir) == output_dir / TRACES_DIRNAME
    assert matches_dir(output_dir) == output_dir / MATCHES_DIRNAME
    assert sample_match_csv(output_dir, stem) == (
        output_dir / "matches" / f"{stem}_targeted_matches.csv"
    )
    assert sample_trace_csv(output_dir, stem) == (
        output_dir / "traces" / f"{stem}_ms1_traces.csv"
    )
    assert sample_tic_png(output_dir, stem) == output_dir / "traces" / f"{stem}_tic.png"
    assert sample_eics_pdf(output_dir, stem) == (
        output_dir / "traces" / f"{stem}_eics.pdf"
    )


def test_resolve_trace_csv_prefers_traces_then_root(tmp_path: Path) -> None:
    output_dir = tmp_path / "results"
    traces = output_dir / "traces"
    traces.mkdir(parents=True)
    stem = "sample_a"
    nested = traces / f"{stem}_ms1_traces.csv"
    legacy = output_dir / f"{stem}_ms1_traces.csv"
    nested.write_text("nested\n", encoding="utf-8")
    legacy.write_text("legacy\n", encoding="utf-8")
    assert resolve_trace_csv(output_dir, stem) == nested

    nested.unlink()
    assert resolve_trace_csv(output_dir, stem) == legacy

    legacy.unlink()
    assert resolve_trace_csv(output_dir, stem) is None


def test_relocate_legacy_traces_moves_tic_trace_and_eic_pdf(tmp_path: Path) -> None:
    output_dir = tmp_path / "results"
    output_dir.mkdir()
    stem = "MONet_61078_Neg"
    (output_dir / f"{stem}_ms1_traces.csv").write_text("t\n", encoding="utf-8")
    (output_dir / f"{stem}_tic.png").write_bytes(b"png")
    (output_dir / f"{stem}_eics.pdf").write_bytes(b"pdf")
    (output_dir / f"{stem}_targeted_matches.csv").write_text("m\n", encoding="utf-8")
    (output_dir / "export_area.csv").write_text("e\n", encoding="utf-8")
    (output_dir / "dashboard.html").write_text("<html></html>", encoding="utf-8")

    moved = relocate_legacy_traces(output_dir)

    traces = output_dir / "traces"
    assert traces.is_dir()
    assert (traces / f"{stem}_ms1_traces.csv").is_file()
    assert (traces / f"{stem}_tic.png").is_file()
    assert (traces / f"{stem}_eics.pdf").is_file()
    assert not (output_dir / f"{stem}_ms1_traces.csv").exists()
    assert not (output_dir / f"{stem}_tic.png").exists()
    assert not (output_dir / f"{stem}_eics.pdf").exists()
    assert (output_dir / f"{stem}_targeted_matches.csv").is_file()
    assert (output_dir / "export_area.csv").is_file()
    assert (output_dir / "dashboard.html").is_file()
    assert len(moved) == 3


def test_relocate_legacy_outputs_moves_matches_and_traces(tmp_path: Path) -> None:
    output_dir = tmp_path / "results"
    output_dir.mkdir()
    stem = "MONet_61078_Neg"
    (output_dir / f"{stem}_targeted_matches.csv").write_text("m\n", encoding="utf-8")
    (output_dir / f"{stem}_ms1_traces.csv").write_text("t\n", encoding="utf-8")
    (output_dir / f"{stem}_tic.png").write_bytes(b"png")
    (output_dir / "export_area.csv").write_text("e\n", encoding="utf-8")
    (output_dir / "dashboard.html").write_text("<html></html>", encoding="utf-8")
    (output_dir / "pipeline_manifest.json").write_text("{}", encoding="utf-8")

    relocate_legacy_outputs(output_dir)

    assert (output_dir / "matches" / f"{stem}_targeted_matches.csv").is_file()
    assert (output_dir / "traces" / f"{stem}_ms1_traces.csv").is_file()
    assert (output_dir / "traces" / f"{stem}_tic.png").is_file()
    assert not (output_dir / f"{stem}_targeted_matches.csv").exists()
    assert not (output_dir / f"{stem}_ms1_traces.csv").exists()
    assert not (output_dir / f"{stem}_tic.png").exists()
    assert (output_dir / "export_area.csv").is_file()
    assert (output_dir / "dashboard.html").is_file()
    assert (output_dir / "pipeline_manifest.json").is_file()


def test_relocate_keeps_nested_copy_if_both_exist(tmp_path: Path) -> None:
    output_dir = tmp_path / "results"
    traces = output_dir / "traces"
    traces.mkdir(parents=True)
    stem = "sample_a"
    nested = traces / f"{stem}_ms1_traces.csv"
    legacy = output_dir / f"{stem}_ms1_traces.csv"
    nested.write_text("nested\n", encoding="utf-8")
    legacy.write_text("legacy\n", encoding="utf-8")

    relocate_legacy_traces(output_dir)

    assert nested.read_text(encoding="utf-8") == "nested\n"
    assert not legacy.exists()


def _minimal_sample(
    output_dir: Path, sample: str, *, traces_in: str, matches_in: str = "root"
) -> None:
    if matches_in == "matches":
        dest = output_dir / "matches"
        dest.mkdir(parents=True, exist_ok=True)
        match_csv = dest / f"{sample}_targeted_matches.csv"
    else:
        match_csv = output_dir / f"{sample}_targeted_matches.csv"
    pd.DataFrame(
        {
            "compound_name": ["Caffeine"],
            "mf_id": [1],
            "observed_mz": [195.0877],
            "observed_rt": [1.1],
            "intensity": [1000.0],
            "target_mz": [195.0877],
            "target_rt": [1.1],
            "mz_error_ppm": [0.1],
            "rt_error": [0.0],
            "polarity": ["positive"],
            "acquisition_time": ["2026-01-01T12:00:00+00:00"],
        }
    ).to_csv(match_csv, index=False)
    traces_df = pd.DataFrame({"time": [1.0, 1.1], "mf_1_Caffeine": [10.0, 20.0]})
    if traces_in == "traces":
        dest = output_dir / "traces"
        dest.mkdir(parents=True, exist_ok=True)
        traces_df.to_csv(dest / f"{sample}_ms1_traces.csv", index=False)
    else:
        traces_df.to_csv(output_dir / f"{sample}_ms1_traces.csv", index=False)


def test_dashboard_reads_nested_matches_and_traces(tmp_path: Path) -> None:
    output_dir = tmp_path / "results"
    output_dir.mkdir()
    _minimal_sample(
        output_dir, "QC_pos_01", traces_in="traces", matches_in="matches"
    )

    synth = HTMLSynthesizer(
        output_dirs=(output_dir,),
        html_output=output_dir / "dashboard.html",
        mz_tolerance_ppm=5.0,
        rt_tolerance=0.5,
    )
    html = synth.render().read_text(encoding="utf-8")
    assert "Caffeine" in html
    assert synth.last_compound_pages == 1


def test_dashboard_relocates_root_matches_and_traces_then_renders(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "results"
    output_dir.mkdir()
    sample = "QC_pos_01"
    _minimal_sample(output_dir, sample, traces_in="root", matches_in="root")
    (output_dir / f"{sample}_tic.png").write_bytes(b"png")

    synth = HTMLSynthesizer(
        output_dirs=(output_dir,),
        html_output=output_dir / "dashboard.html",
        mz_tolerance_ppm=5.0,
        rt_tolerance=0.5,
    )
    html = synth.render().read_text(encoding="utf-8")
    assert "Caffeine" in html
    assert (output_dir / "matches" / f"{sample}_targeted_matches.csv").is_file()
    assert (output_dir / "traces" / f"{sample}_ms1_traces.csv").is_file()
    assert (output_dir / "traces" / f"{sample}_tic.png").is_file()
    assert not (output_dir / f"{sample}_targeted_matches.csv").exists()
    assert not (output_dir / f"{sample}_ms1_traces.csv").exists()
    assert not (output_dir / f"{sample}_tic.png").exists()
    root_names = {p.name for p in output_dir.iterdir() if p.is_file()}
    assert "dashboard.html" in root_names
    assert not any(name.endswith("_targeted_matches.csv") for name in root_names)
