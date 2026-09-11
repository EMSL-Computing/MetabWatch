"""License file is present and matches the required Battelle / PNNL terms."""

from __future__ import annotations

from pathlib import Path


def test_license_file_contains_required_terms(project_root: Path) -> None:
    license_path = project_root / "LICENSE"
    assert license_path.is_file()
    text = license_path.read_text(encoding="utf-8")
    assert "Copyright Battelle Memorial Institute 2026" in text
    assert "Redistribution and use in source and binary forms" in text
    assert "Redistributions of source code must retain the above copyright notice" in text
    assert "Redistributions in binary form must reproduce the above copyright notice" in text
    assert "PACIFIC NORTHWEST NATIONAL LABORATORY" in text
    assert "DE-AC05-76RL01830" in text


def test_pyproject_points_at_license_file(project_root: Path) -> None:
    pyproject = (project_root / "pyproject.toml").read_text(encoding="utf-8")
    assert 'license = { file = "LICENSE" }' in pyproject
