"""Tests for GUI form validation and config resolution (no tkinter)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from metabwatch.gui.validation import (
    GuiRunRequest,
    preset_summary_text,
    resolve_config,
    validate_request,
)


def test_preset_summary_mentions_method_defaults() -> None:
    text = preset_summary_text("hilic_metab_pnnl", "targeted")
    assert "0.8" in text
    assert "1000" in text
    assert "QC_Metab" in text

    rp = preset_summary_text("rp_metab_pnnl", "untargeted")
    assert "0.4" in text or "0.4" in rp
    assert "20000" in rp
    assert "Pool" in rp

    eclipse_h = preset_summary_text("hilic_metab_olympic_eclipse01", "targeted")
    assert "0.6" in eclipse_h
    eclipse_rp = preset_summary_text("rp_metab_olympic_eclipse01", "untargeted")
    assert "0.2" in eclipse_rp


def test_validate_preset_requires_existing_input(tmp_path: Path) -> None:
    req = GuiRunRequest(
        source="preset",
        method="hilic_metab_pnnl",
        search="targeted",
        input_folder=str(tmp_path / "missing"),
        output_folder=str(tmp_path / "out"),
    )
    err = validate_request(req)
    assert err is not None
    assert "Input folder" in err


def test_validate_preset_ok(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    raw.mkdir()
    req = GuiRunRequest(
        source="preset",
        method="hilic_metab_pnnl",
        search="targeted",
        input_folder=str(raw),
        output_folder=str(tmp_path / "out"),
    )
    assert validate_request(req) is None


def test_validate_eclipse01_preset_ok(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    raw.mkdir()
    req = GuiRunRequest(
        source="preset",
        method="rp_metab_olympic_eclipse01",
        search="targeted",
        input_folder=str(raw),
        output_folder=str(tmp_path / "out"),
    )
    assert validate_request(req) is None


def test_validate_json_requires_file(tmp_path: Path) -> None:
    req = GuiRunRequest(
        source="json",
        config_path=str(tmp_path / "nope.json"),
    )
    err = validate_request(req)
    assert err is not None
    assert "not found" in err.lower()


def test_validate_json_rejects_non_json(tmp_path: Path) -> None:
    path = tmp_path / "cfg.txt"
    path.write_text("{}", encoding="utf-8")
    req = GuiRunRequest(source="json", config_path=str(path))
    err = validate_request(req)
    assert err is not None
    assert ".json" in err


def test_resolve_preset_builds_config(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    raw.mkdir()
    out = tmp_path / "out"
    req = GuiRunRequest(
        source="preset",
        method="rp_metab_pnnl",
        search="untargeted",
        input_folder=str(raw),
        output_folder=str(out),
    )
    cfg = resolve_config(req)
    assert cfg.search_space.mode == "untargeted"
    assert cfg.watcher.raw_dir == raw.resolve()
    assert cfg.processor.output_dir == out.resolve()
    assert cfg.processor.params_path.is_file()
    assert cfg.processor.min_area == 20000.0
    assert cfg.polarity is None
    assert cfg.watcher.project_id == ""


def test_resolve_preset_project_id(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    raw.mkdir()
    req = GuiRunRequest(
        source="preset",
        method="rp_metab_pnnl",
        search="untargeted",
        project_id=" 25-02 ",
        input_folder=str(raw),
        output_folder=str(tmp_path / "out"),
    )
    cfg = resolve_config(req)
    assert cfg.watcher.project_id == "25-02"
    assert "(?i)Pool" in (cfg.watcher.sample_name_regex or "")


def test_resolve_preset_polarity_positive(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    raw.mkdir()
    req = GuiRunRequest(
        source="preset",
        method="rp_metab_pnnl",
        search="untargeted",
        polarity="positive",
        input_folder=str(raw),
        output_folder=str(tmp_path / "out"),
    )
    assert validate_request(req) is None
    cfg = resolve_config(req)
    assert cfg.polarity == "positive"


def test_validate_preset_rejects_bad_polarity(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    raw.mkdir()
    req = GuiRunRequest(
        source="preset",
        method="hilic_metab_pnnl",
        search="targeted",
        polarity="both",
        input_folder=str(raw),
        output_folder=str(tmp_path / "out"),
    )
    err = validate_request(req)
    assert err is not None
    assert "polarity" in err.lower()


def test_resolve_json_loads_config(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    raw.mkdir()
    out = tmp_path / "out"
    # Minimal simplified config using packaged preset assets via absolute paths
    from metabwatch.presets import build_pipeline_config

    # Use build_pipeline_config only to locate a real corems.toml for the JSON
    seed = build_pipeline_config("hilic_metab_pnnl", "targeted", raw, out)
    payload = {
        "input_folder": str(raw),
        "output_folder": str(out),
        "corems_params": str(seed.processor.params_path),
        "targeted": True,
        "qc_compounds": str(seed.processor.standards_csv),
        "sample_name_regex": "QC_Metab_(.+)",
        "mz_tolerance_ppm": 7.0,
        "rt_tolerance": 1.1,
        "min_area": 1234,
    }
    cfg_path = tmp_path / "run.json"
    cfg_path.write_text(json.dumps(payload), encoding="utf-8")

    req = GuiRunRequest(source="json", config_path=str(cfg_path))
    assert validate_request(req) is None
    cfg = resolve_config(req)
    assert cfg.processor.mz_tolerance_ppm == 7.0
    assert cfg.processor.rt_tolerance == 1.1
    assert cfg.processor.min_area == 1234.0
    assert cfg.search_space.mode == "targeted"


def test_resolve_raises_on_invalid_preset(tmp_path: Path) -> None:
    req = GuiRunRequest(
        source="preset",
        method="hilic_metab_pnnl",
        search="targeted",
        input_folder="",
        output_folder=str(tmp_path / "out"),
    )
    with pytest.raises(ValueError, match="Input folder"):
        resolve_config(req)
