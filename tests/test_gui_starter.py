"""Tests for the Custom JSON starter-folder writer (no tkinter)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from metabwatch.config import load_pipeline_config
from metabwatch.gui.starter import (
    CONFIG_FILENAME,
    COREMS_FILENAME,
    DEFAULT_CONFIG_FOLDER_NAME,
    QC_CSV_FILENAME,
    RP_MIN_AREA,
    RP_MZ_TOLERANCE_PPM,
    RP_RT_TOLERANCE,
    RP_TARGETED_REGEX,
    RP_UNTARGETED_REGEX,
    StarterSettings,
    next_available_config_dir,
    normalize_config_folder_name,
    requested_config_dir,
    rp_packaged_dir,
    settings_from_form,
    write_rp_starter_folder,
)
from metabwatch.gui.validation import GuiRunRequest, resolve_config, validate_request


def _settings(
    tmp_path: Path,
    *,
    targeted: bool,
    mz: float = RP_MZ_TOLERANCE_PPM,
    rt: float = RP_RT_TOLERANCE,
    min_area: float = RP_MIN_AREA,
    regex: str = "",
    top_n: int = 100,
) -> StarterSettings:
    raw = tmp_path / "raw"
    raw.mkdir(exist_ok=True)
    return StarterSettings(
        input_folder=raw,
        output_folder=tmp_path / "out",
        targeted=targeted,
        mz_tolerance_ppm=mz,
        rt_tolerance=rt,
        min_area=min_area,
        sample_name_regex=regex,
        top_n=top_n,
    )


def test_targeted_write_three_files_and_loads(tmp_path: Path) -> None:
    dest = tmp_path / "starter"
    result = write_rp_starter_folder(dest, _settings(tmp_path, targeted=True))

    json_path = dest / CONFIG_FILENAME
    toml_path = dest / COREMS_FILENAME
    csv_path = dest / QC_CSV_FILENAME
    assert json_path.is_file()
    assert toml_path.is_file()
    assert csv_path.is_file()
    assert result.config_path == json_path

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["targeted"] is True
    assert "top_n" not in payload
    assert Path(payload["qc_compounds"]) == csv_path.resolve()
    assert Path(payload["corems_params"]) == toml_path.resolve()
    assert Path(payload["qc_compounds"]).is_file()
    assert Path(payload["corems_params"]).is_file()
    assert Path(payload["input_folder"]).is_dir()
    assert Path(payload["corems_params"]).is_absolute()
    assert Path(payload["qc_compounds"]).is_absolute()
    assert Path(payload["input_folder"]).is_absolute()
    assert Path(payload["output_folder"]).is_absolute()
    assert set(payload) == {
        "input_folder",
        "output_folder",
        "corems_params",
        "targeted",
        "qc_compounds",
        "sample_name_regex",
        "mz_tolerance_ppm",
        "rt_tolerance",
        "min_area",
    }

    cfg = load_pipeline_config(json_path)
    assert cfg.search_space.mode == "targeted"
    assert cfg.processor.params_path == toml_path.resolve()
    assert cfg.processor.standards_csv == csv_path.resolve()


def test_untargeted_write_skips_qc_csv_and_loads(tmp_path: Path) -> None:
    dest = tmp_path / "starter"
    write_rp_starter_folder(dest, _settings(tmp_path, targeted=False))

    assert (dest / CONFIG_FILENAME).is_file()
    assert (dest / COREMS_FILENAME).is_file()
    assert not (dest / QC_CSV_FILENAME).exists()

    payload = json.loads((dest / CONFIG_FILENAME).read_text(encoding="utf-8"))
    assert payload["targeted"] is False
    assert "qc_compounds" not in payload
    assert payload["top_n"] == 100
    assert payload["sample_name_regex"] == RP_UNTARGETED_REGEX

    cfg = load_pipeline_config(dest / CONFIG_FILENAME)
    assert cfg.search_space.mode == "untargeted"
    assert cfg.search_space.top_n == 100


def test_numeric_defaults_match_rp_thresholds(tmp_path: Path) -> None:
    dest = tmp_path / "starter"
    write_rp_starter_folder(dest, _settings(tmp_path, targeted=True))
    payload = json.loads((dest / CONFIG_FILENAME).read_text(encoding="utf-8"))
    assert payload["mz_tolerance_ppm"] == RP_MZ_TOLERANCE_PPM
    assert payload["rt_tolerance"] == RP_RT_TOLERANCE
    assert payload["min_area"] == RP_MIN_AREA
    assert payload["sample_name_regex"] == RP_TARGETED_REGEX

    cfg = load_pipeline_config(dest / CONFIG_FILENAME)
    assert cfg.processor.mz_tolerance_ppm == 5.0
    assert cfg.processor.rt_tolerance == 0.4
    assert cfg.processor.min_area == 20000.0


def test_packaged_rp_assets_unchanged_after_write(tmp_path: Path) -> None:
    packaged = rp_packaged_dir()
    toml_src = packaged / COREMS_FILENAME
    csv_src = packaged / QC_CSV_FILENAME
    toml_before = toml_src.read_bytes()
    csv_before = csv_src.read_bytes()
    toml_mtime = toml_src.stat().st_mtime_ns
    csv_mtime = csv_src.stat().st_mtime_ns

    dest = tmp_path / "starter"
    write_rp_starter_folder(dest, _settings(tmp_path, targeted=True))

    assert toml_src.read_bytes() == toml_before
    assert csv_src.read_bytes() == csv_before
    assert toml_src.stat().st_mtime_ns == toml_mtime
    assert csv_src.stat().st_mtime_ns == csv_mtime
    assert (dest / COREMS_FILENAME).read_bytes() == toml_before
    assert (dest / QC_CSV_FILENAME).read_bytes() == csv_before


def test_gui_validation_accepts_written_json(tmp_path: Path) -> None:
    dest = tmp_path / "starter"
    result = write_rp_starter_folder(dest, _settings(tmp_path, targeted=True))
    req = GuiRunRequest(source="json", config_path=str(result.config_path))
    assert validate_request(req) is None
    cfg = resolve_config(req)
    assert cfg.search_space.mode == "targeted"
    assert cfg.processor.min_area == RP_MIN_AREA


def test_custom_tolerances_and_regex_round_trip(tmp_path: Path) -> None:
    dest = tmp_path / "starter"
    write_rp_starter_folder(
        dest,
        _settings(
            tmp_path,
            targeted=False,
            mz=7.5,
            rt=1.25,
            min_area=1234,
            regex=r"(?i)PoolQC",
            top_n=25,
        ),
    )
    payload = json.loads((dest / CONFIG_FILENAME).read_text(encoding="utf-8"))
    assert payload["mz_tolerance_ppm"] == 7.5
    assert payload["rt_tolerance"] == 1.25
    assert payload["min_area"] == 1234
    assert payload["sample_name_regex"] == r"(?i)PoolQC"
    assert payload["top_n"] == 25
    cfg = load_pipeline_config(dest / CONFIG_FILENAME)
    assert cfg.processor.mz_tolerance_ppm == 7.5
    assert cfg.search_space.top_n == 25


def test_next_available_config_dir_uses_free_name(tmp_path: Path) -> None:
    parent = tmp_path / "save"
    parent.mkdir()
    dest = next_available_config_dir(parent, DEFAULT_CONFIG_FOLDER_NAME)
    assert dest == parent / DEFAULT_CONFIG_FOLDER_NAME
    assert not dest.exists()


def test_next_available_config_dir_skips_occupied_folder(tmp_path: Path) -> None:
    parent = tmp_path / "save"
    occupied = parent / DEFAULT_CONFIG_FOLDER_NAME
    occupied.mkdir(parents=True)
    (occupied / CONFIG_FILENAME).write_text("{}", encoding="utf-8")
    dest = next_available_config_dir(parent, DEFAULT_CONFIG_FOLDER_NAME)
    assert dest == parent / f"{DEFAULT_CONFIG_FOLDER_NAME}_2"
    assert (occupied / CONFIG_FILENAME).read_text(encoding="utf-8") == "{}"


def test_next_available_config_dir_reuses_empty_folder(tmp_path: Path) -> None:
    parent = tmp_path / "save"
    empty = parent / DEFAULT_CONFIG_FOLDER_NAME
    empty.mkdir(parents=True)
    assert next_available_config_dir(parent, DEFAULT_CONFIG_FOLDER_NAME) == empty


def test_next_available_config_dir_skips_taken_suffixes(tmp_path: Path) -> None:
    parent = tmp_path / "save"
    parent.mkdir()
    for name in (DEFAULT_CONFIG_FOLDER_NAME, f"{DEFAULT_CONFIG_FOLDER_NAME}_2"):
        taken = parent / name
        taken.mkdir()
        (taken / "keep.txt").write_text("n", encoding="utf-8")
    dest = next_available_config_dir(parent, DEFAULT_CONFIG_FOLDER_NAME)
    assert dest == parent / f"{DEFAULT_CONFIG_FOLDER_NAME}_3"


def test_write_into_next_available_leaves_existing_folder(tmp_path: Path) -> None:
    parent = tmp_path / "save"
    parent.mkdir()
    first = write_rp_starter_folder(
        next_available_config_dir(parent, DEFAULT_CONFIG_FOLDER_NAME),
        _settings(tmp_path, targeted=True),
    )
    original = first.config_path.read_text(encoding="utf-8")
    second_dest = next_available_config_dir(parent, DEFAULT_CONFIG_FOLDER_NAME)
    assert second_dest == parent / f"{DEFAULT_CONFIG_FOLDER_NAME}_2"
    write_rp_starter_folder(
        second_dest,
        _settings(tmp_path, targeted=True, mz=9.0),
    )
    assert first.config_path.read_text(encoding="utf-8") == original
    payload = json.loads(
        (second_dest / CONFIG_FILENAME).read_text(encoding="utf-8")
    )
    assert payload["mz_tolerance_ppm"] == 9.0


def test_folder_name_rejects_separators() -> None:
    with pytest.raises(ValueError, match="slashes"):
        normalize_config_folder_name("a/b")
    with pytest.raises(ValueError, match="required"):
        normalize_config_folder_name("  ")


def test_requested_config_dir_requires_existing_parent(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Save-in"):
        requested_config_dir(tmp_path / "missing", DEFAULT_CONFIG_FOLDER_NAME)


def test_refuse_overwrite_unless_requested(tmp_path: Path) -> None:
    dest = tmp_path / "starter"
    settings = _settings(tmp_path, targeted=True)
    write_rp_starter_folder(dest, settings)
    with pytest.raises(FileExistsError, match="already exist"):
        write_rp_starter_folder(dest, settings, overwrite=False)
    write_rp_starter_folder(
        dest,
        _settings(tmp_path, targeted=True, mz=9.0),
        overwrite=True,
    )
    payload = json.loads((dest / CONFIG_FILENAME).read_text(encoding="utf-8"))
    assert payload["mz_tolerance_ppm"] == 9.0


def test_refuse_packaged_rp_destination() -> None:
    settings = StarterSettings(
        input_folder="/tmp/raw",
        output_folder="/tmp/out",
        targeted=True,
    )
    with pytest.raises(ValueError, match="packaged RP"):
        write_rp_starter_folder(rp_packaged_dir(), settings)


def test_settings_from_form_defaults_and_errors(tmp_path: Path) -> None:
    raw = str(tmp_path / "raw")
    out = str(tmp_path / "out")
    ok = settings_from_form(
        input_folder=raw,
        output_folder=out,
        targeted=True,
        mz_tolerance_ppm="5",
        rt_tolerance="0.4",
        min_area="20000",
        sample_name_regex="",
    )
    assert ok.resolved_regex() == RP_TARGETED_REGEX
    assert ok.mz_tolerance_ppm == 5.0

    with pytest.raises(ValueError, match="Input folder"):
        settings_from_form(
            input_folder="  ",
            output_folder=out,
            targeted=True,
            mz_tolerance_ppm="5",
            rt_tolerance="0.4",
            min_area="20000",
            sample_name_regex="",
        )
    with pytest.raises(ValueError, match="m/z tolerance"):
        settings_from_form(
            input_folder=raw,
            output_folder=out,
            targeted=True,
            mz_tolerance_ppm="nope",
            rt_tolerance="0.4",
            min_area="20000",
            sample_name_regex="",
        )
    with pytest.raises(ValueError, match="Top N"):
        settings_from_form(
            input_folder=raw,
            output_folder=out,
            targeted=False,
            mz_tolerance_ppm="5",
            rt_tolerance="0.4",
            min_area="20000",
            sample_name_regex="",
            top_n="0",
        )


def test_starter_button_stays_enabled_on_preset_source() -> None:
    import tkinter as tk

    from metabwatch.gui.app import MetabWatchApp

    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("tkinter display required")
    root.withdraw()
    try:
        app = MetabWatchApp(root)
        assert app.source_var.get() == "preset"
        assert str(app.starter_btn.cget("text")) == "Create custom config…"
        assert str(app.starter_btn.cget("state")) == "normal"
        app.source_var.set("json")
        app._update_source_enabled()
        assert str(app.starter_btn.cget("state")) == "normal"
        assert str(app.config_entry.cget("state")) == "normal"
        app.source_var.set("preset")
        app._update_source_enabled()
        assert str(app.starter_btn.cget("state")) == "normal"
        assert str(app.config_entry.cget("state")) == "disabled"
    finally:
        root.destroy()
