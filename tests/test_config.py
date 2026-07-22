"""Unit tests for simplified and legacy pipeline config loading."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from metabwatch.config import load_pipeline_config


def _write_json(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_simplified_targeted_loads_paths_and_mode(
    tmp_path: Path, project_root: Path
) -> None:
    config_path = _write_json(
        tmp_path / "targeted.json",
        {
            "input_folder": "data/raw_positive",
            "output_folder": "data/results_hilic_pos",
            "corems_params": "data/corems_params/monet_hilic_corems_lcms_params.toml",
            "targeted": True,
            "qc_compounds": "data/qc_search_space/hilic_qc_search.csv",
            "sample_name_regex": "QC_Metab_(.+)",
            "mz_tolerance_ppm": 4.0,
            "rt_tolerance": 0.8,
            "min_area": 1000,
        },
    )

    cfg = load_pipeline_config(config_path, project_root)

    assert cfg.watcher.raw_dir == project_root / "data/raw_positive"
    assert cfg.processor.output_dir == project_root / "data/results_hilic_pos"
    assert cfg.processor.params_path == (
        project_root / "data/corems_params/monet_hilic_corems_lcms_params.toml"
    )
    assert cfg.processor.standards_csv == (
        project_root / "data/qc_search_space/hilic_qc_search.csv"
    )
    assert cfg.search_space.mode == "targeted"
    assert cfg.search_space.csv_path == cfg.processor.standards_csv
    assert cfg.watcher.sample_name_regex == "QC_Metab_(.+)"
    assert cfg.processor.mz_tolerance_ppm == 4.0
    assert cfg.processor.rt_tolerance == 0.8
    assert cfg.processor.min_area == 1000
    assert cfg.synthesizer.mz_tolerance_ppm == 4.0
    assert cfg.synthesizer.rt_tolerance == 0.8
    assert cfg.synthesizer.html_output == (
        project_root / "data/results_hilic_pos/dashboard.html"
    )
    assert cfg.state.pipeline_manifest == (
        project_root / "data/results_hilic_pos/pipeline_manifest.json"
    )


def test_simplified_untargeted_without_qc_compounds(
    tmp_path: Path, project_root: Path
) -> None:
    config_path = _write_json(
        tmp_path / "untargeted.json",
        {
            "input_folder": "data/raw_positive",
            "output_folder": "data/results_hilic_pos_untargeted",
            "corems_params": "data/corems_params/monet_hilic_corems_lcms_params.toml",
            "targeted": False,
            "sample_name_regex": "QC_Metab_(.+)",
            "top_n": 50,
        },
    )

    cfg = load_pipeline_config(config_path, project_root)

    assert cfg.search_space.mode == "untargeted"
    assert cfg.search_space.top_n == 50
    expected_csv = (
        project_root
        / "data/results_hilic_pos_untargeted/untargeted_search_space.csv"
    )
    assert cfg.search_space.csv_path == expected_csv
    assert cfg.processor.standards_csv == expected_csv
    assert cfg.watcher.sample_name_regex == "QC_Metab_(.+)"
    # Defaults when optional knobs omitted
    assert cfg.processor.mz_tolerance_ppm == 5.0
    assert cfg.processor.rt_tolerance == 0.5
    assert cfg.processor.min_area == 5e3
    assert cfg.processor.plot_tic is True
    assert cfg.processor.integrate_mass_features is True
    assert cfg.watcher.poll_interval_sec == 10.0
    assert cfg.watcher.discovery_mode == "hybrid"


def test_discovery_mode_explicit_poll(tmp_path: Path, project_root: Path) -> None:
    config_path = _write_json(
        tmp_path / "poll_mode.json",
        {
            "input_folder": "data/raw_positive",
            "output_folder": "data/results_hilic_pos",
            "corems_params": "data/corems_params/params.toml",
            "targeted": True,
            "qc_compounds": "data/qc_search_space/hilic_qc_search.csv",
            "sample_name_regex": "QC_Metab_(.+)",
            "discovery_mode": "poll",
        },
    )

    cfg = load_pipeline_config(config_path, project_root)
    assert cfg.watcher.discovery_mode == "poll"


def test_discovery_mode_invalid_raises(tmp_path: Path, project_root: Path) -> None:
    config_path = _write_json(
        tmp_path / "bad_mode.json",
        {
            "input_folder": "data/raw_positive",
            "output_folder": "data/results_hilic_pos",
            "corems_params": "data/corems_params/params.toml",
            "targeted": True,
            "qc_compounds": "data/qc_search_space/hilic_qc_search.csv",
            "sample_name_regex": "QC_Metab_(.+)",
            "discovery_mode": "notify",
        },
    )

    with pytest.raises(ValueError, match="discovery_mode"):
        load_pipeline_config(config_path, project_root)


def test_legacy_discovery_mode(tmp_path: Path, project_root: Path) -> None:
    config_path = _write_json(
        tmp_path / "legacy_watchdog.json",
        {
            "processor": {
                "standards_csv": "data/qc_search_space/hilic_qc_search.csv",
                "params_path": "data/corems_params/params.toml",
                "output_dir": "data/results_hilic_pos",
            },
            "watcher": {
                "raw_dir": "data/raw_positive",
                "discovery_mode": "WATCHDOG",
            },
        },
    )

    cfg = load_pipeline_config(config_path, project_root)
    assert cfg.watcher.discovery_mode == "watchdog"


def test_simplified_targeted_missing_qc_compounds_raises(
    tmp_path: Path, project_root: Path
) -> None:
    config_path = _write_json(
        tmp_path / "bad.json",
        {
            "input_folder": "data/raw_positive",
            "output_folder": "data/results_hilic_pos",
            "corems_params": "data/corems_params/params.toml",
            "targeted": True,
            "sample_name_regex": "QC_Metab_(.+)",
        },
    )

    with pytest.raises(ValueError, match="qc_compounds"):
        load_pipeline_config(config_path, project_root)


def test_simplified_missing_sample_name_regex_raises(
    tmp_path: Path, project_root: Path
) -> None:
    config_path = _write_json(
        tmp_path / "no_regex.json",
        {
            "input_folder": "data/raw_positive",
            "output_folder": "data/results",
            "corems_params": "data/corems_params/params.toml",
            "targeted": False,
        },
    )

    with pytest.raises(ValueError, match="sample_name_regex"):
        load_pipeline_config(config_path, project_root)


def test_legacy_nested_still_loads(tmp_path: Path, project_root: Path) -> None:
    config_path = _write_json(
        tmp_path / "legacy.json",
        {
            "processor": {
                "standards_csv": "data/qc_search_space/hilic_qc_search.csv",
                "params_path": "data/corems_params/monet_hilic_corems_lcms_params.toml",
                "output_dir": "data/results_hilic_pos",
                "mz_tolerance_ppm": 4.0,
                "rt_tolerance": 0.8,
                "min_area": 1000,
            },
            "watcher": {
                "raw_dir": "data/raw_positive",
                "sample_name_regex": "QC_Metab_(.+)",
            },
            "synthesizer": {"debounce_sec": 5.0},
        },
    )

    cfg = load_pipeline_config(config_path, project_root)

    assert cfg.search_space.mode == "targeted"
    assert cfg.watcher.raw_dir == project_root / "data/raw_positive"
    assert cfg.processor.output_dir == project_root / "data/results_hilic_pos"
    assert cfg.processor.standards_csv == (
        project_root / "data/qc_search_space/hilic_qc_search.csv"
    )
    assert cfg.watcher.sample_name_regex == "QC_Metab_(.+)"
    assert cfg.processor.mz_tolerance_ppm == 4.0


def test_legacy_untargeted_still_loads(
    tmp_path: Path, project_root: Path
) -> None:
    config_path = _write_json(
        tmp_path / "legacy_untargeted.json",
        {
            "processor": {
                "params_path": "data/corems_params/params.toml",
                "output_dir": "data/results_out",
            },
            "watcher": {"raw_dir": "data/raw_positive"},
            "search_space": {"mode": "untargeted", "top_n": 25},
        },
    )

    cfg = load_pipeline_config(config_path, project_root)

    assert cfg.search_space.mode == "untargeted"
    assert cfg.search_space.top_n == 25
    assert cfg.search_space.csv_path == (
        project_root / "data/results_out/untargeted_search_space.csv"
    )
    assert cfg.watcher.sample_name_regex is None


def test_mixed_formats_rejected(tmp_path: Path, project_root: Path) -> None:
    config_path = _write_json(
        tmp_path / "mixed.json",
        {
            "input_folder": "data/raw_positive",
            "output_folder": "data/results",
            "corems_params": "data/corems_params/params.toml",
            "targeted": True,
            "qc_compounds": "data/qc.csv",
            "sample_name_regex": "QC_",
            "processor": {"output_dir": "data/other"},
        },
    )

    with pytest.raises(ValueError, match="mixes simplified and legacy"):
        load_pipeline_config(config_path, project_root)


def test_example_configs_load(project_root: Path) -> None:
    """Smoke-load the shipped example configs from data/."""
    targeted = load_pipeline_config(
        project_root / "data/hilic_pipeline_config.json", project_root
    )
    untargeted = load_pipeline_config(
        project_root / "data/hilic_pipeline_config_untargeted.json",
        project_root,
    )

    assert targeted.search_space.mode == "targeted"
    assert targeted.watcher.sample_name_regex == "QC_Metab_(.+)"
    assert untargeted.search_space.mode == "untargeted"
    assert untargeted.search_space.top_n == 100


def test_absolute_paths_preserved(tmp_path: Path, project_root: Path) -> None:
    abs_input = tmp_path / "raws"
    abs_output = tmp_path / "out"
    abs_params = tmp_path / "params.toml"
    abs_qc = tmp_path / "qc.csv"
    config_path = _write_json(
        tmp_path / "abs.json",
        {
            "input_folder": str(abs_input),
            "output_folder": str(abs_output),
            "corems_params": str(abs_params),
            "targeted": True,
            "qc_compounds": str(abs_qc),
            "sample_name_regex": ".*",
        },
    )

    cfg = load_pipeline_config(config_path, project_root)

    assert cfg.watcher.raw_dir == abs_input
    assert cfg.processor.output_dir == abs_output
    assert cfg.processor.params_path == abs_params
    assert cfg.processor.standards_csv == abs_qc
