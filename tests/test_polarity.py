"""Unit tests for manifest polarity lock and dashboard polarity labels."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from metabwatch.pipeline import apply_configured_polarity
from metabwatch.presets import build_pipeline_config
from metabwatch.processor.orchestrator import ProcessResult, ProcessorOrchestrator
from metabwatch.state.manifest_store import ManifestStateStore
from metabwatch.synthesis.synthesizer import HTMLSynthesizer


def test_manifest_sets_run_polarity_on_first_complete(tmp_path):
    store = ManifestStateStore(tmp_path / "pipeline_manifest.json")
    raw = tmp_path / "pos.raw"
    raw.write_bytes(b"x")
    out = tmp_path / "out.csv"
    trace = tmp_path / "trace.csv"
    out.write_text("a\n", encoding="utf-8")
    trace.write_text("a\n", encoding="utf-8")

    assert store.get_run_polarity() is None
    store.mark_in_progress(raw)
    store.mark_completed(
        raw_file=raw,
        output_csv=out,
        trace_csv=trace,
        polarity="Positive",
    )
    assert store.get_run_polarity() == "positive"

    payload = json.loads((tmp_path / "pipeline_manifest.json").read_text(encoding="utf-8"))
    assert payload["polarity"] == "positive"
    entry = payload["entries"][0]
    assert entry["polarity"] == "positive"


def test_manifest_rejects_mixed_polarity_on_complete(tmp_path):
    store = ManifestStateStore(tmp_path / "pipeline_manifest.json")
    pos = tmp_path / "pos.raw"
    neg = tmp_path / "neg.raw"
    pos.write_bytes(b"p")
    neg.write_bytes(b"n")
    out = tmp_path / "out.csv"
    trace = tmp_path / "trace.csv"
    out.write_text("a\n", encoding="utf-8")
    trace.write_text("a\n", encoding="utf-8")

    store.mark_in_progress(pos)
    store.mark_completed(pos, out, trace, polarity="positive")
    store.mark_in_progress(neg)
    with pytest.raises(ValueError, match="Polarity mismatch"):
        store.mark_completed(neg, out, trace, polarity="negative")


def test_manifest_set_run_polarity_and_reload(tmp_path):
    path = tmp_path / "pipeline_manifest.json"
    store = ManifestStateStore(path)
    assert store.set_run_polarity("negative") == "negative"
    assert store.set_run_polarity("NEGATIVE") == "negative"
    with pytest.raises(ValueError, match="Polarity mismatch"):
        store.set_run_polarity("positive")

    reloaded = ManifestStateStore(path)
    assert reloaded.get_run_polarity() == "negative"


def test_manifest_infers_polarity_from_completed_entries(tmp_path):
    path = tmp_path / "pipeline_manifest.json"
    path.write_text(
        json.dumps(
            {
                "updated_at": "2026-01-01T00:00:00+00:00",
                "entries": [
                    {
                        "raw_file": str(tmp_path / "a.raw"),
                        "fingerprint": "abc",
                        "size": 1,
                        "mtime": 1.0,
                        "status": "completed",
                        "attempts": 1,
                        "updated_at": "2026-01-01T00:00:00+00:00",
                        "polarity": "positive",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    store = ManifestStateStore(path)
    assert store.get_run_polarity() == "positive"


def test_orchestrator_polarity_mismatch_not_retryable(monkeypatch, tmp_path):
    def _raise_mismatch(**kwargs):
        raise ValueError(
            "Polarity mismatch: file neg.raw is 'negative' "
            "but this run is locked to 'positive'."
        )

    monkeypatch.setattr(
        "metabwatch.processor.orchestrator.process_raw_to_observed_features_df",
        _raise_mismatch,
    )
    orch = ProcessorOrchestrator(
        standards_csv=tmp_path / "standards.csv",
        params_path=tmp_path / "params.toml",
        output_dir=tmp_path,
        mz_tolerance_ppm=5.0,
        rt_tolerance=0.5,
        min_area=1000.0,
        plot_eics=False,
        plot_tic=False,
        integrate_mass_features=False,
        cluster_mass_features=False,
    )
    result = orch.process_single_raw(
        tmp_path / "neg.raw",
        expected_polarity="positive",
    )
    assert result.status == "failed"
    assert result.retryable is False
    assert "Polarity mismatch" in (result.error or "")


def test_orchestrator_returns_polarity_on_success(monkeypatch, tmp_path):
    def _fake_process(**kwargs):
        df = pd.DataFrame({"compound_name": ["x"], "intensity": [1.0]})
        df.attrs["acquisition_time"] = "2026-01-01T00:00:00+00:00"
        df.attrs["polarity"] = "positive"
        return df

    monkeypatch.setattr(
        "metabwatch.processor.orchestrator.process_raw_to_observed_features_df",
        _fake_process,
    )
    orch = ProcessorOrchestrator(
        standards_csv=tmp_path / "standards.csv",
        params_path=tmp_path / "params.toml",
        output_dir=tmp_path,
        mz_tolerance_ppm=5.0,
        rt_tolerance=0.5,
        min_area=1000.0,
        plot_eics=False,
        plot_tic=False,
        integrate_mass_features=False,
        cluster_mass_features=False,
    )
    result = orch.process_single_raw(tmp_path / "pos.raw")
    assert result.status == "completed"
    assert result.polarity == "positive"


def test_format_run_polarity_label():
    assert HTMLSynthesizer.format_run_polarity_label({"positive"}) == "positive"
    assert HTMLSynthesizer.format_run_polarity_label({"negative"}) == "negative"
    assert HTMLSynthesizer.format_run_polarity_label(set()) == "unknown"
    label = HTMLSynthesizer.format_run_polarity_label({"positive", "negative"})
    assert label.startswith("mixed")
    assert "positive" in label and "negative" in label


def test_dashboard_html_includes_polarity(tmp_path):
    output_dir = tmp_path / "results"
    compounds_dir = output_dir / "compounds"
    output_dir.mkdir()
    compounds_dir.mkdir()

    sample = "QC_pos_01"
    match_csv = output_dir / f"{sample}_targeted_matches.csv"
    trace_csv = output_dir / f"{sample}_ms1_traces.csv"
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
    pd.DataFrame(
        {
            "time": [1.0, 1.1, 1.2],
            "mf_1_Caffeine": [10.0, 20.0, 10.0],
        }
    ).to_csv(trace_csv, index=False)

    synth = HTMLSynthesizer(
        output_dirs=(output_dir,),
        html_output=output_dir / "dashboard.html",
        mz_tolerance_ppm=5.0,
        rt_tolerance=0.5,
    )
    path = synth.render()
    html = path.read_text(encoding="utf-8")
    assert "Polarity:" in html
    assert "positive" in html
    assert synth.last_polarity_label == "positive"

    compound_html = (compounds_dir / "caffeine.html").read_text(encoding="utf-8")
    assert "Polarity:" in compound_html
    assert "positive" in compound_html


def test_dashboard_html_warns_on_mixed_polarity(tmp_path):
    output_dir = tmp_path / "results"
    compounds_dir = output_dir / "compounds"
    output_dir.mkdir()
    compounds_dir.mkdir()

    for sample, polarity, acq in [
        ("QC_pos_01", "positive", "2026-01-01T12:00:00+00:00"),
        ("QC_neg_01", "negative", "2026-01-02T12:00:00+00:00"),
    ]:
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
                "polarity": [polarity],
                "acquisition_time": [acq],
            }
        ).to_csv(output_dir / f"{sample}_targeted_matches.csv", index=False)
        pd.DataFrame(
            {
                "time": [1.0, 1.1],
                "mf_1_Caffeine": [10.0, 20.0],
            }
        ).to_csv(output_dir / f"{sample}_ms1_traces.csv", index=False)

    synth = HTMLSynthesizer(
        output_dirs=(output_dir,),
        html_output=output_dir / "dashboard.html",
        mz_tolerance_ppm=5.0,
        rt_tolerance=0.5,
    )
    html = synth.render().read_text(encoding="utf-8")
    assert synth.last_polarity_label.startswith("mixed")
    assert "mixed polarities are not supported" in html
    assert "color:#b42318" in html


def test_process_result_defaults():
    result = ProcessResult(raw_file=Path("x.raw"), status="completed")
    assert result.polarity is None


def test_apply_configured_polarity_locks_before_samples(tmp_path: Path) -> None:
    cfg = build_pipeline_config(
        "hilic_metab_pnnl",
        "targeted",
        tmp_path / "raw",
        tmp_path / "out",
        polarity="negative",
    )
    store = ManifestStateStore(tmp_path / "out" / "pipeline_manifest.json")
    assert store.get_run_polarity() is None
    locked = apply_configured_polarity(cfg, store)
    assert locked == "negative"
    assert store.get_run_polarity() == "negative"
    payload = json.loads(store.manifest_json.read_text(encoding="utf-8"))
    assert payload["polarity"] == "negative"


def test_apply_configured_polarity_unset_leaves_unlocked(tmp_path: Path) -> None:
    cfg = build_pipeline_config(
        "hilic_metab_pnnl",
        "targeted",
        tmp_path / "raw",
        tmp_path / "out",
    )
    store = ManifestStateStore(tmp_path / "out" / "pipeline_manifest.json")
    assert apply_configured_polarity(cfg, store) is None
    assert store.get_run_polarity() is None


def test_apply_configured_polarity_conflicts_with_manifest(tmp_path: Path) -> None:
    cfg = build_pipeline_config(
        "hilic_metab_pnnl",
        "targeted",
        tmp_path / "raw",
        tmp_path / "out",
        polarity="positive",
    )
    store = ManifestStateStore(tmp_path / "out" / "pipeline_manifest.json")
    store.set_run_polarity("negative")
    with pytest.raises(ValueError, match="config requests"):
        apply_configured_polarity(cfg, store)
    assert store.get_run_polarity() == "negative"
