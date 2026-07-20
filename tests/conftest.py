"""Shared pytest fixtures and runtime setup for MetabWatch tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from metabwatch.corems_runtime import ensure_dotnet_runtime

# Configure Mono before any test module imports CoreMS via the processor package.
ensure_dotnet_runtime()


@pytest.fixture
def project_root(pytestconfig) -> Path:
    """Pytest project root (directory containing pyproject.toml)."""
    return Path(pytestconfig.rootpath)
