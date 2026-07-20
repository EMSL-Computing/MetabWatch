"""Shared pytest fixtures and runtime setup for MetabWatch tests."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from corems_runtime import ensure_dotnet_runtime  # noqa: E402

# Configure Mono before any test module imports CoreMS via the processor package.
ensure_dotnet_runtime()
