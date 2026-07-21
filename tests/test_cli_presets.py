"""CLI tests for preset flags vs advanced --config."""

from __future__ import annotations

from pathlib import Path

import pytest

from metabwatch.pipeline import parse_args, resolve_config_from_args, main


def test_parse_preset_args() -> None:
    ns = parse_args(
        [
            "--method",
            "hilic",
            "--search",
            "targeted",
            "--input",
            "raw",
            "--output",
            "out",
        ]
    )
    assert ns.method == "hilic"
    assert ns.search == "targeted"
    assert ns.input == Path("raw")
    assert ns.output == Path("out")
    assert ns.config is None


def test_parse_short_input_output_aliases() -> None:
    ns = parse_args(
        [
            "--method",
            "rp",
            "--search",
            "untargeted",
            "-i",
            "in_dir",
            "-o",
            "out_dir",
        ]
    )
    assert ns.input == Path("in_dir")
    assert ns.output == Path("out_dir")


def test_parse_config_still_works() -> None:
    ns = parse_args(["--config", "foo.json"])
    assert ns.config == Path("foo.json")
    assert ns.method is None


def test_resolve_preset_builds_config(tmp_path: Path) -> None:
    ns = parse_args(
        [
            "--method",
            "hilic",
            "--search",
            "targeted",
            "--input",
            str(tmp_path / "raw"),
            "--output",
            str(tmp_path / "out"),
        ]
    )
    cfg = resolve_config_from_args(ns)
    assert cfg.search_space.mode == "targeted"
    assert cfg.processor.params_path.is_file()
    assert cfg.watcher.sample_name_regex == r"QC_Metab_(.+)"


def test_resolve_rejects_mixed_args(tmp_path: Path) -> None:
    ns = parse_args(
        [
            "--config",
            str(tmp_path / "c.json"),
            "--method",
            "hilic",
            "--search",
            "targeted",
            "--input",
            str(tmp_path),
            "--output",
            str(tmp_path),
        ]
    )
    with pytest.raises(ValueError, match="not both"):
        resolve_config_from_args(ns)


def test_resolve_rejects_incomplete_preset() -> None:
    ns = parse_args(["--method", "hilic", "--search", "targeted"])
    with pytest.raises(ValueError, match="Missing"):
        resolve_config_from_args(ns)


def test_resolve_rejects_neither() -> None:
    ns = parse_args([])
    with pytest.raises(ValueError, match="Provide"):
        resolve_config_from_args(ns)


def test_main_rejects_mixed_args(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = main(
        [
            "--config",
            str(tmp_path / "c.json"),
            "--method",
            "hilic",
            "--search",
            "targeted",
            "--input",
            str(tmp_path),
            "--output",
            str(tmp_path),
        ]
    )
    assert code == 2
    err = capsys.readouterr().err
    assert "not both" in err
