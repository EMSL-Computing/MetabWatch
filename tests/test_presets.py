"""Unit tests for built-in RP / HILIC pipeline presets."""

from __future__ import annotations

from pathlib import Path

import pytest

from metabwatch.presets import build_pipeline_config


@pytest.mark.parametrize(
    "method,search,expect_mode,mz,rt,min_area,regex_fragment",
    [
        ("hilic", "targeted", "targeted", 5.0, 0.8, 1000.0, "QC_Metab_"),
        ("hilic", "untargeted", "untargeted", 5.0, 0.8, 1000.0, "Pooled"),
        ("rp", "targeted", "targeted", 5.0, 0.4, 20000.0, "QC_Metab_"),
        ("rp", "untargeted", "untargeted", 5.0, 0.4, 20000.0, "Pooled"),
    ],
)
def test_build_pipeline_config_matrix(
    method: str,
    search: str,
    expect_mode: str,
    mz: float,
    rt: float,
    min_area: float,
    regex_fragment: str,
    tmp_path: Path,
) -> None:
    inp = tmp_path / "raw"
    out = tmp_path / "out"
    inp.mkdir()
    cfg = build_pipeline_config(method, search, inp, out)

    assert cfg.search_space.mode == expect_mode
    assert cfg.processor.mz_tolerance_ppm == mz
    assert cfg.processor.rt_tolerance == rt
    assert cfg.processor.min_area == min_area
    assert cfg.watcher.raw_dir == inp.resolve()
    assert cfg.processor.output_dir == out.resolve()
    assert regex_fragment.lower() in (cfg.watcher.sample_name_regex or "").lower()
    assert cfg.processor.params_path.is_file()
    assert cfg.processor.params_path.name == "corems.toml"
    if expect_mode == "targeted":
        assert cfg.processor.standards_csv.is_file()
        assert cfg.processor.standards_csv.name == "qc_compounds.csv"
        assert cfg.search_space.csv_path == cfg.processor.standards_csv
    else:
        assert cfg.search_space.csv_path == out.resolve() / "untargeted_search_space.csv"
        assert cfg.search_space.top_n == 100


def test_unknown_method_raises(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="method"):
        build_pipeline_config("gc", "targeted", tmp_path, tmp_path)


def test_unknown_search_raises(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="search"):
        build_pipeline_config("hilic", "semi", tmp_path, tmp_path)


def test_assets_live_under_package_presets() -> None:
    """CoreMS/QC files are package data, not the old data/ paths."""
    cfg = build_pipeline_config("hilic", "targeted", Path("/tmp/in"), Path("/tmp/out"))
    path_str = str(cfg.processor.params_path)
    assert "presets" in path_str
    assert "hilic" in path_str
    assert "corems_params" not in path_str
