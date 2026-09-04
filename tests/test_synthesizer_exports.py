"""Unit tests for wide CSV exports and Area CV on the dashboard index."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from metabwatch.synthesis.synthesizer import HTMLSynthesizer, PLOTLY_JS_FILENAME


def _write_sample(
    output_dir: Path,
    sample: str,
    *,
    acquisition_time: str,
    rows: list[dict],
    include_area: bool = True,
    extra_trace_cols: dict[str, list] | None = None,
) -> None:
    """Write a minimal matches + traces pair for one sample."""
    match_path = output_dir / f"{sample}_targeted_matches.csv"
    trace_path = output_dir / f"{sample}_ms1_traces.csv"

    match_rows = []
    for row in rows:
        record = {
            "mf_id": row["mf_id"],
            "filename": f"{sample}.raw",
            "compound_name": row["compound_name"],
            "ion_type": "[M+H]+",
            "polarity": "positive",
            "target_mz": row.get("target_mz", 100.0),
            "target_rt": row.get("target_rt", 1.0),
            "observed_mz": row.get("observed_mz", 100.0),
            "observed_rt": row.get("observed_rt", 1.0),
            "mz_error_ppm": row.get("mz_error_ppm", 0.0),
            "rt_error": row.get("rt_error", 0.0),
            "intensity": row["intensity"],
            "acquisition_time": acquisition_time,
        }
        if include_area:
            record["area"] = row["area"]
        match_rows.append(record)

    pd.DataFrame(match_rows).to_csv(match_path, index=False)
    traces = {
        "time": [0.5, 1.0, 1.5],
        "tic": [1.0, 2.0, 1.0],
        "acquisition_time": [acquisition_time] * 3,
    }
    if extra_trace_cols:
        traces.update(extra_trace_cols)
    pd.DataFrame(traces).to_csv(trace_path, index=False)


def _json_const(html: str, name: str) -> dict:
    """Parse a ``const name = {...};`` JSON object from dashboard HTML."""
    prefix = f"const {name} = "
    start = html.index(prefix) + len(prefix)
    obj, _end = json.JSONDecoder().raw_decode(html[start:].lstrip())
    return obj


def test_export_area_and_area_cv_with_area_column(tmp_path: Path) -> None:
    output_dir = tmp_path / "results"
    output_dir.mkdir()
    html_output = output_dir / "dashboard.html"

    _write_sample(
        output_dir,
        "sample_a",
        acquisition_time="2026-01-01T10:00:00+00:00",
        rows=[
            {
                "mf_id": 0,
                "compound_name": "Alpha",
                "intensity": 100.0,
                "area": 1000.0,
                "mz_error_ppm": 1.0,
            }
        ],
    )
    _write_sample(
        output_dir,
        "sample_b",
        acquisition_time="2026-01-01T11:00:00+00:00",
        rows=[
            {
                "mf_id": 0,
                "compound_name": "Alpha",
                "intensity": 200.0,
                "area": 3000.0,
                "mz_error_ppm": 2.0,
            }
        ],
    )

    synth = HTMLSynthesizer(
        output_dirs=(output_dir,),
        html_output=html_output,
        mz_tolerance_ppm=5.0,
        rt_tolerance=0.5,
    )
    result = synth.render()
    assert result == html_output
    assert html_output.exists()

    index_html = html_output.read_text(encoding="utf-8")
    assert "Area CV" in index_html
    assert "Intensity CV" in index_html
    # area values 1000, 3000 → mean 2000, std (ddof=0) = 1000 → CV 50%
    assert "50.00%" in index_html
    assert 'id="landing-cv"' in index_html
    assert "Reproducibility overview (CV)" in index_html
    assert "Plotly.newPlot('landing-cv'" in index_html
    # Dual histogram series embedded in the page JSON
    assert '"name": "Intensity CV"' in index_html
    assert '"name": "Area CV"' in index_html
    assert '"barmode": "overlay"' in index_html

    assert "area" in synth.last_export_paths
    assert "height" in synth.last_export_paths

    area_df = pd.read_csv(synth.last_export_paths["area"])
    height_df = pd.read_csv(synth.last_export_paths["height"])

    assert list(area_df.columns) == ["compound_name", "sample_a", "sample_b"]
    alpha_area = area_df.set_index("compound_name").loc["Alpha"]
    assert alpha_area["sample_a"] == pytest.approx(1000.0)
    assert alpha_area["sample_b"] == pytest.approx(3000.0)

    alpha_height = height_df.set_index("compound_name").loc["Alpha"]
    assert alpha_height["sample_a"] == pytest.approx(100.0)
    assert alpha_height["sample_b"] == pytest.approx(200.0)


def test_export_area_without_area_column_is_empty_and_cv_na(tmp_path: Path) -> None:
    output_dir = tmp_path / "results"
    output_dir.mkdir()
    html_output = output_dir / "dashboard.html"

    _write_sample(
        output_dir,
        "sample_a",
        acquisition_time="2026-01-01T10:00:00+00:00",
        rows=[
            {
                "mf_id": 0,
                "compound_name": "Beta",
                "intensity": 100.0,
                "area": 999.0,  # ignored when include_area=False
            }
        ],
        include_area=False,
    )
    _write_sample(
        output_dir,
        "sample_b",
        acquisition_time="2026-01-01T11:00:00+00:00",
        rows=[
            {
                "mf_id": 0,
                "compound_name": "Beta",
                "intensity": 200.0,
                "area": 999.0,
            }
        ],
        include_area=False,
    )

    synth = HTMLSynthesizer(
        output_dirs=(output_dir,),
        html_output=html_output,
        mz_tolerance_ppm=5.0,
        rt_tolerance=0.5,
    )
    synth.render()

    index_html = html_output.read_text(encoding="utf-8")
    assert "Area CV" in index_html
    assert "n/a" in index_html
    assert 'id="landing-cv"' in index_html
    assert '"name": "Intensity CV"' in index_html
    assert '"name": "Area CV"' in index_html

    area_df = pd.read_csv(synth.last_export_paths["area"])
    beta = area_df.set_index("compound_name").loc["Beta"]
    assert pd.isna(beta["sample_a"])
    assert pd.isna(beta["sample_b"])


def test_landing_cv_histogram_data_matches_mean_cv(tmp_path: Path) -> None:
    """Histogram x values should match per-compound Intensity/Area CVs."""
    output_dir = tmp_path / "results"
    output_dir.mkdir()
    html_output = output_dir / "dashboard.html"

    _write_sample(
        output_dir,
        "sample_a",
        acquisition_time="2026-01-01T10:00:00+00:00",
        rows=[
            {
                "mf_id": 0,
                "compound_name": "Alpha",
                "intensity": 100.0,
                "area": 1000.0,
            },
            {
                "mf_id": 1,
                "compound_name": "Beta",
                "intensity": 50.0,
                "area": 400.0,
                "target_mz": 200.0,
                "target_rt": 2.0,
                "observed_mz": 200.0,
                "observed_rt": 2.0,
            },
        ],
    )
    _write_sample(
        output_dir,
        "sample_b",
        acquisition_time="2026-01-01T11:00:00+00:00",
        rows=[
            {
                "mf_id": 0,
                "compound_name": "Alpha",
                "intensity": 300.0,
                "area": 3000.0,
            },
            {
                "mf_id": 1,
                "compound_name": "Beta",
                "intensity": 50.0,
                "area": 600.0,
                "target_mz": 200.0,
                "target_rt": 2.0,
                "observed_mz": 200.0,
                "observed_rt": 2.0,
            },
        ],
    )

    synth = HTMLSynthesizer(
        output_dirs=(output_dir,),
        html_output=html_output,
        mz_tolerance_ppm=5.0,
        rt_tolerance=0.5,
    )
    synth.render()

    # Build compounds dict the same way the synthesizer does for the plot helper.
    # Alpha intensity 100,300 → mean 200, std 100 → CV 50%
    # Alpha area 1000,3000 → mean 2000, std 1000 → CV 50%
    # Beta intensity 50,50 → CV 0%
    # Beta area 400,600 → mean 500, std 100 → CV 20%
    _samples, compounds, _polarities = synth._build_dataset()
    cv_plot = synth._build_landing_cv_histogram(compounds)

    by_name = {trace["name"]: trace for trace in cv_plot["data"]}
    assert set(by_name) == {"Intensity CV", "Area CV"}
    assert sorted(by_name["Intensity CV"]["x"]) == pytest.approx([0.0, 50.0])
    assert sorted(by_name["Area CV"]["x"]) == pytest.approx([20.0, 50.0])
    assert by_name["Intensity CV"]["xbins"] == by_name["Area CV"]["xbins"]
    assert by_name["Intensity CV"]["xbins"]["size"] == 5.0
    assert cv_plot["layout"]["barmode"] == "overlay"
    assert any(shape.get("x0") == 30 for shape in cv_plot["layout"]["shapes"])


def test_landing_cv_threshold_summary_matches_histogram(tmp_path: Path) -> None:
    """Summary table uses the same CVs as the histogram (below 20% / 30%)."""
    output_dir = tmp_path / "results"
    output_dir.mkdir()
    html_output = output_dir / "dashboard.html"

    _write_sample(
        output_dir,
        "sample_a",
        acquisition_time="2026-01-01T10:00:00+00:00",
        rows=[
            {
                "mf_id": 0,
                "compound_name": "Alpha",
                "intensity": 100.0,
                "area": 1000.0,
            },
            {
                "mf_id": 1,
                "compound_name": "Beta",
                "intensity": 50.0,
                "area": 400.0,
            },
        ],
    )
    _write_sample(
        output_dir,
        "sample_b",
        acquisition_time="2026-01-01T11:00:00+00:00",
        rows=[
            {
                "mf_id": 0,
                "compound_name": "Alpha",
                "intensity": 300.0,
                "area": 3000.0,
            },
            {
                "mf_id": 1,
                "compound_name": "Beta",
                "intensity": 50.0,
                "area": 600.0,
            },
        ],
    )

    synth = HTMLSynthesizer(
        output_dirs=(output_dir,),
        html_output=html_output,
        mz_tolerance_ppm=5.0,
        rt_tolerance=0.5,
    )
    synth.render()
    index_html = html_output.read_text(encoding="utf-8")

    # Intensity CVs 0% and 50% → <20%: 1/2 (50%); <30%: 1/2 (50%)
    # Area CVs 20% and 50% → <20%: 0/2 (0%); <30%: 1/2 (50%)
    assert 'id="landing-cv-summary"' in index_html
    assert 'class="cv-overview"' in index_html
    assert "&lt; 20% CV" in index_html
    assert "&lt; 30% CV" in index_html
    assert "<strong>50%</strong> (1/2)" in index_html
    assert "<strong>0%</strong> (0/2)" in index_html

    _samples, compounds, _polarities = synth._build_dataset()
    intensity_cvs, area_cvs = synth._collect_landing_cvs(compounds)
    assert synth._count_cv_below(intensity_cvs, 20.0) == (1, 2)
    assert synth._count_cv_below(intensity_cvs, 30.0) == (1, 2)
    assert synth._count_cv_below(area_cvs, 20.0) == (0, 2)
    assert synth._count_cv_below(area_cvs, 30.0) == (1, 2)


def test_cv_below_cell_empty() -> None:
    assert HTMLSynthesizer._format_cv_below_cell(0, 0) == "<strong>0%</strong> (0/0)"
    assert HTMLSynthesizer._format_cv_below_cell(1, 2) == "<strong>50%</strong> (1/2)"


def test_write_placeholder_if_missing(tmp_path: Path) -> None:
    """Placeholder dashboard appears before first synthesis; not overwritten."""
    output_dir = tmp_path / "results"
    html_output = output_dir / "dashboard.html"
    synth = HTMLSynthesizer(
        output_dirs=(output_dir,),
        html_output=html_output,
        mz_tolerance_ppm=5.0,
        rt_tolerance=0.5,
    )

    path = synth.write_placeholder_if_missing()
    assert path == html_output
    assert html_output.is_file()
    text = html_output.read_text(encoding="utf-8")
    assert "Processing first sample" in text
    assert "Refresh" in text or "refresh" in text
    assert "cdn.plot.ly" not in text

    # Second call must not clobber an existing file (placeholder or real).
    html_output.write_text("KEEP_ME", encoding="utf-8")
    synth.write_placeholder_if_missing()
    assert html_output.read_text(encoding="utf-8") == "KEEP_ME"


def test_dashboard_uses_local_plotly_offline(tmp_path: Path) -> None:
    """Dashboard HTML must load vendored Plotly.js (no CDN) for offline use."""
    output_dir = tmp_path / "results"
    output_dir.mkdir()
    html_output = output_dir / "dashboard.html"

    _write_sample(
        output_dir,
        "sample_a",
        acquisition_time="2026-01-01T10:00:00+00:00",
        rows=[
            {
                "mf_id": 0,
                "compound_name": "Alpha",
                "intensity": 100.0,
                "area": 1000.0,
            }
        ],
    )

    synth = HTMLSynthesizer(
        output_dirs=(output_dir,),
        html_output=html_output,
        mz_tolerance_ppm=5.0,
        rt_tolerance=0.5,
    )
    synth.render()

    plotly_dest = output_dir / PLOTLY_JS_FILENAME
    assert plotly_dest.is_file()
    assert plotly_dest.stat().st_size > 1000

    index_html = html_output.read_text(encoding="utf-8")
    assert "cdn.plot.ly" not in index_html
    assert f'src="{PLOTLY_JS_FILENAME}"' in index_html
    assert "Plotly.newPlot" in index_html

    compound_html = (output_dir / "compounds" / "alpha.html").read_text(encoding="utf-8")
    assert "cdn.plot.ly" not in compound_html
    assert f'src="../{PLOTLY_JS_FILENAME}"' in compound_html


def test_compound_page_eic_first_and_next_link(tmp_path: Path) -> None:
    output_dir = tmp_path / "results"
    output_dir.mkdir()
    html_output = output_dir / "dashboard.html"

    _write_sample(
        output_dir,
        "sample_a",
        acquisition_time="2026-01-01T10:00:00+00:00",
        rows=[
            {"mf_id": 0, "compound_name": "Alpha", "intensity": 100.0, "area": 1000.0},
            {"mf_id": 1, "compound_name": "Beta", "intensity": 50.0, "area": 400.0},
        ],
    )

    HTMLSynthesizer(
        output_dirs=(output_dir,),
        html_output=html_output,
        mz_tolerance_ppm=5.0,
        rt_tolerance=0.5,
    ).render()

    alpha = (output_dir / "compounds" / "alpha.html").read_text(encoding="utf-8")
    beta = (output_dir / "compounds" / "beta.html").read_text(encoding="utf-8")
    assert "Back to compound index" in alpha
    assert "Previous compound: Beta" in alpha
    assert "Next compound: Beta" in alpha
    assert alpha.index("Previous compound: Beta") < alpha.index("Next compound: Beta")
    assert 'href="beta.html"' in alpha
    assert "Previous compound: Alpha" in beta
    assert "Next compound: Alpha" in beta
    assert 'href="alpha.html"' in beta
    assert alpha.index("EIC overlay") < alpha.index("Across-sample metrics")
    assert beta.index("EIC overlay") < beta.index("Across-sample metrics")


def test_eic_overlay_marks_apex_when_only_target_column_exists(tmp_path: Path) -> None:
    """A match with observed_rt gets a solid EIC and apex marker even without mf_*."""
    output_dir = tmp_path / "results"
    output_dir.mkdir()
    html_output = output_dir / "dashboard.html"

    alpha_row = {
        "mf_id": 0,
        "compound_name": "Alpha",
        "intensity": 5.0e7,
        "area": 1.0e8,
        "observed_rt": 1.0,
    }
    _write_sample(
        output_dir,
        "sample_a",
        acquisition_time="2026-01-01T10:00:00+00:00",
        rows=[alpha_row],
        extra_trace_cols={
            "mf_0_Alpha": [10.0, 50.0, 10.0],
            "target_Alpha": [8.0, 40.0, 8.0],
        },
    )
    _write_sample(
        output_dir,
        "sample_b",
        acquisition_time="2026-01-01T11:00:00+00:00",
        rows=[alpha_row],
        extra_trace_cols={"target_Alpha": [9.0, 45.0, 9.0]},
    )
    _write_sample(
        output_dir,
        "sample_c",
        acquisition_time="2026-01-01T12:00:00+00:00",
        rows=[
            {
                "mf_id": 1,
                "compound_name": "Gamma",
                "intensity": 10.0,
                "area": 20.0,
                "target_mz": 200.0,
                "target_rt": 2.0,
                "observed_mz": 200.0,
                "observed_rt": 2.0,
            }
        ],
        extra_trace_cols={"target_Alpha": [1.0, 2.0, 1.0]},
    )

    synth = HTMLSynthesizer(
        output_dirs=(output_dir,),
        html_output=html_output,
        mz_tolerance_ppm=5.0,
        rt_tolerance=0.5,
    )
    synth.render()

    compound_html = (output_dir / "compounds" / "alpha.html").read_text(encoding="utf-8")
    eic_plot = _json_const(compound_html, "eicPlot")
    traces = eic_plot["data"]

    line_traces = [t for t in traces if t.get("mode") != "markers" and "line" in t]
    marker_traces = [t for t in traces if t.get("mode") == "markers"]
    dash_by_name = {t["name"]: t["line"].get("dash", "solid") for t in line_traces}

    assert len(line_traces) == 3
    # sample_a has mf_*; sample_b is a match with only target_*; both solid.
    assert dash_by_name["2026-01-01 10:00 UTC"] == "solid"
    assert dash_by_name["2026-01-01 11:00 UTC"] == "solid"
    # sample_c has no Alpha match: dotted, no apex.
    assert dash_by_name["2026-01-01 12:00 UTC"] == "dot"

    marker_names = {t["name"] for t in marker_traces}
    assert marker_names == {
        "2026-01-01 10:00 UTC peak",
        "2026-01-01 11:00 UTC peak",
    }
    for marker in marker_traces:
        assert marker["marker"]["color"] == "#f5f5f5"
        assert marker["marker"]["line"]["color"] == "#1a1a1a"
        line = next(t for t in line_traces if t["name"] + " peak" == marker["name"])
        assert marker["marker"]["color"] != line["line"]["color"]
