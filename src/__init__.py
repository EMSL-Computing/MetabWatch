"""MetabWatch: automated LC–MS metabolomics QC watcher for Thermo .raw files."""

from __future__ import annotations

__all__ = ["__version__", "get_version"]

# Fallback when package metadata is unavailable (editable/dev edge cases).
_FALLBACK_VERSION = "0.2.0"


def get_version() -> str:
    """Return the installed package version string.

    Prefers ``importlib.metadata`` (matches ``pyproject.toml`` / wheel
    metadata). Falls back to a hard-coded string when metadata is missing
    (e.g. incomplete freezes).
    """
    try:
        from importlib.metadata import PackageNotFoundError, version

        try:
            return version("metabwatch")
        except PackageNotFoundError:
            pass
    except Exception:
        pass
    return _FALLBACK_VERSION


__version__ = get_version()
