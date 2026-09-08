"""Unit tests for built-in PNNL Standard RP / HILIC pipeline presets."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from metabwatch.presets import build_pipeline_config


def _qc_rows(method: str) -> list[dict[str, str]]:
    path = Path(__file__).resolve().parents[1] / "src" / "presets" / method / "qc_compounds.csv"
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


_PRESET_TO_SOURCE = {
    "Alanine": "L-Alanine",
    "Malic acid": "L-Malic acid",
    "Tartaric acid": "L-Tartaric acid",
}


def _parse_optional_float(value: str | None) -> float | None:
    text = (value or "").strip()
    if not text:
        return None
    return float(text)


def _source_compounds() -> dict[str, dict[str, str]]:
    path = Path(__file__).resolve().parents[1] / "data" / "QC_Metab_26-06.csv"
    with path.open(newline="", encoding="utf-8") as handle:
        return {row["compound_name"]: row for row in csv.DictReader(handle)}


_HILIC_METHODS = ("hilic_metab_pnnl", "hilic_metab_olympic_eclipse01")
_RP_METHODS = ("rp_metab_pnnl", "rp_metab_olympic_eclipse01")


@pytest.mark.parametrize(
    "method,search,expect_mode,mz,rt,min_area,regex_fragment",
    [
        ("hilic_metab_pnnl", "targeted", "targeted", 5.0, 0.8, 1000.0, "QC_Metab_"),
        ("hilic_metab_pnnl", "untargeted", "untargeted", 5.0, 0.8, 1000.0, "Pool"),
        ("rp_metab_pnnl", "targeted", "targeted", 5.0, 0.4, 20000.0, "QC_Metab_"),
        ("rp_metab_pnnl", "untargeted", "untargeted", 5.0, 0.4, 20000.0, "Pool"),
        (
            "hilic_metab_olympic_eclipse01",
            "targeted",
            "targeted",
            5.0,
            0.6,
            1000.0,
            "QC_Metab_",
        ),
        (
            "hilic_metab_olympic_eclipse01",
            "untargeted",
            "untargeted",
            5.0,
            0.6,
            1000.0,
            "Pool",
        ),
        (
            "rp_metab_olympic_eclipse01",
            "targeted",
            "targeted",
            5.0,
            0.2,
            20000.0,
            "QC_Metab_",
        ),
        (
            "rp_metab_olympic_eclipse01",
            "untargeted",
            "untargeted",
            5.0,
            0.2,
            20000.0,
            "Pool",
        ),
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
    assert cfg.polarity is None
    assert cfg.watcher.project_id == ""
    assert cfg.processor.params_path.is_file()
    assert cfg.processor.params_path.name == "corems.toml"
    if expect_mode == "targeted":
        assert cfg.processor.standards_csv.is_file()
        assert cfg.processor.standards_csv.name == "qc_compounds.csv"
        assert cfg.search_space.csv_path == cfg.processor.standards_csv
    else:
        assert cfg.search_space.csv_path == out.resolve() / "untargeted_search_space.csv"
        assert cfg.search_space.top_n == 100


def test_preset_project_id_optional(tmp_path: Path) -> None:
    cfg = build_pipeline_config(
        "hilic_metab_pnnl",
        "untargeted",
        tmp_path,
        tmp_path,
        project_id=" 25-02 ",
    )
    assert cfg.watcher.project_id == "25-02"
    assert "(?i)Pool" in (cfg.watcher.sample_name_regex or "")


def test_preset_polarity_optional(tmp_path: Path) -> None:
    cfg = build_pipeline_config(
        "hilic_metab_pnnl",
        "targeted",
        tmp_path,
        tmp_path,
        polarity="positive",
    )
    assert cfg.polarity == "positive"


def test_preset_invalid_polarity_raises(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="polarity"):
        build_pipeline_config(
            "hilic_metab_pnnl",
            "targeted",
            tmp_path,
            tmp_path,
            polarity="both",
        )


def test_unknown_method_raises(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="method"):
        build_pipeline_config("gc", "targeted", tmp_path, tmp_path)


def test_unknown_search_raises(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="search"):
        build_pipeline_config("hilic_metab_pnnl", "semi", tmp_path, tmp_path)


def test_assets_live_under_package_presets() -> None:
    """CoreMS/QC files are package data, not the old data/ paths."""
    cfg = build_pipeline_config("hilic_metab_pnnl", "targeted", Path("/tmp/in"), Path("/tmp/out"))
    path_str = str(cfg.processor.params_path)
    assert "presets" in path_str
    assert "hilic_metab_pnnl" in path_str
    assert "corems_params" not in path_str


def test_presets_omit_compounds_without_method_rt() -> None:
    """Drop compounds with no numeric RT(HILIC) from HILIC, no numeric RT(RP) from RP."""
    source = _source_compounds()
    source_to_preset = {v: k for k, v in _PRESET_TO_SOURCE.items()}
    hilic_names = {
        row["compound_name"] for method in _HILIC_METHODS for row in _qc_rows(method)
    }
    rp_names = {row["compound_name"] for method in _RP_METHODS for row in _qc_rows(method)}

    for source_name, src in source.items():
        name = source_to_preset.get(source_name, source_name)
        if _parse_optional_float(src["rt_hilic"]) is None:
            assert name not in hilic_names, source_name
        if _parse_optional_float(src["rt_rp"]) is None:
            assert name not in rp_names, source_name


def test_presets_omit_ions_without_numeric_mass() -> None:
    """Drop [M+H]+ / [M-H]- rows when the Aug 2026 list has no numeric mass for that ion."""
    source = _source_compounds()
    source_to_preset = {v: k for k, v in _PRESET_TO_SOURCE.items()}

    def ion_names(methods: tuple[str, ...], ion_type: str) -> set[str]:
        return {
            row["compound_name"]
            for method in methods
            for row in _qc_rows(method)
            if row["ion_type"].strip() == ion_type
        }

    hilic_pos = ion_names(_HILIC_METHODS, "[M+H]+")
    hilic_neg = ion_names(_HILIC_METHODS, "[M-H]-")
    rp_pos = ion_names(_RP_METHODS, "[M+H]+")
    rp_neg = ion_names(_RP_METHODS, "[M-H]-")

    for source_name, src in source.items():
        name = source_to_preset.get(source_name, source_name)
        if _parse_optional_float(src["mz_m_plus_h"]) is None:
            assert name not in hilic_pos, source_name
            assert name not in rp_pos, source_name
        if _parse_optional_float(src["mz_m_minus_h"]) is None:
            assert name not in hilic_neg, source_name
            assert name not in rp_neg, source_name


def test_preset_qc_rts_match_aug_2026_list() -> None:
    """Packaged QC retention times come from the Olympic LC / Eclipse 01 list."""
    source = _source_compounds()
    for method, rt_column in (
        ("hilic_metab_pnnl", "rt_hilic"),
        ("hilic_metab_olympic_eclipse01", "rt_hilic"),
        ("rp_metab_pnnl", "rt_rp"),
        ("rp_metab_olympic_eclipse01", "rt_rp"),
    ):
        for row in _qc_rows(method):
            source_name = _PRESET_TO_SOURCE.get(row["compound_name"], row["compound_name"])
            expected = _parse_optional_float(source[source_name][rt_column])
            assert expected is not None, (method, row["compound_name"])
            assert float(row["retention_time"]) == pytest.approx(expected, abs=0.005)


def test_hilic_presets_omit_problematic_qc_compounds() -> None:
    """HILIC targeted lists drop Hesperetin, Syringaldehide, and negative L-Glutamine."""
    for method in _HILIC_METHODS:
        rows = _qc_rows(method)
        names_by_polarity = {
            "positive": {row["compound_name"] for row in rows if row["polarity"] == "positive"},
            "negative": {row["compound_name"] for row in rows if row["polarity"] == "negative"},
        }
        assert "Hesperetin" not in names_by_polarity["positive"]
        assert "Hesperetin" not in names_by_polarity["negative"]
        assert "Syringaldehide" not in names_by_polarity["positive"]
        assert "Syringaldehide" not in names_by_polarity["negative"]
        assert "L-Glutamine" not in names_by_polarity["negative"]
        assert "L-Glutamine" in names_by_polarity["positive"]


def test_rp_presets_keep_hilic_omitted_qc_compounds() -> None:
    """RP targeted lists are unchanged by the HILIC-only QC trim."""
    for method in _RP_METHODS:
        names = {row["compound_name"] for row in _qc_rows(method)}
        assert {"Hesperetin", "Syringaldehide", "L-Glutamine"} <= names


def test_eclipse01_presets_use_own_asset_folders() -> None:
    hilic = build_pipeline_config(
        "hilic_metab_olympic_eclipse01", "targeted", Path("/tmp/in"), Path("/tmp/out")
    )
    rp = build_pipeline_config(
        "rp_metab_olympic_eclipse01", "targeted", Path("/tmp/in"), Path("/tmp/out")
    )
    assert "hilic_metab_olympic_eclipse01" in str(hilic.processor.params_path)
    assert "rp_metab_olympic_eclipse01" in str(rp.processor.params_path)
    assert hilic.processor.standards_csv is not None
    assert rp.processor.standards_csv is not None
    assert hilic.processor.standards_csv.parent == hilic.processor.params_path.parent
    assert rp.processor.standards_csv.parent == rp.processor.params_path.parent
