"""MetabWatch desktop GUI (Windows-first; also usable on macOS)."""

from __future__ import annotations

import os

__all__ = ["main"]


def main(argv: list[str] | None = None) -> int:
    """Launch the MetabWatch GUI application."""
    # Must run before matplotlib is imported (pipeline → processor → plots).
    os.environ.setdefault("MPLBACKEND", "Agg")

    from metabwatch.gui.app import main as app_main

    return app_main(argv)
