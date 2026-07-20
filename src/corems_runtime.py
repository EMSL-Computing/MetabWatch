"""Configure the .NET/Mono runtime before any CoreMS / pythonnet import.

On Apple Silicon, the system Mono.framework is often x86_64-only while the
repo venv is arm64. Homebrew Mono (`/opt/homebrew/lib/libmonosgen-2.0.dylib`)
is the usual fix. Call :func:`ensure_dotnet_runtime` before importing CoreMS.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_CONFIGURED = False


def _candidate_mono_libs() -> list[Path]:
    paths: list[Path] = []
    env = os.environ.get("METABWATCH_MONO_LIB") or os.environ.get("PYTHONNET_MONO_LIB")
    if env:
        paths.append(Path(env))
    # Apple Silicon Homebrew first, then Intel Homebrew / custom prefixes.
    paths.extend(
        [
            Path("/opt/homebrew/lib/libmonosgen-2.0.dylib"),
            Path("/usr/local/lib/libmonosgen-2.0.dylib"),
        ]
    )
    return paths


def ensure_dotnet_runtime() -> None:
    """Select a loadable Mono library for pythonnet when needed.

    Safe to call multiple times. No-op on non-macOS or when no candidate
    library exists (default pythonnet discovery is left alone).
    """
    global _CONFIGURED
    if _CONFIGURED:
        return
    _CONFIGURED = True

    if sys.platform != "darwin":
        return

    libmono = next((p for p in _candidate_mono_libs() if p.is_file()), None)
    if libmono is None:
        return

    try:
        from clr_loader import get_mono
        from pythonnet import set_runtime
    except ImportError:
        return

    try:
        set_runtime(get_mono(libmono=str(libmono)))
    except Exception:
        # Runtime may already be set/loaded; let subsequent imports surface errors.
        return
