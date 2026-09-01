"""Smoke tests for the Tkinter GUI shell."""

from __future__ import annotations

import tkinter as tk

import pytest

from metabwatch.presets import METHOD_KEYS


def test_gui_app_builds_with_all_method_radios() -> None:
    """Startup must not reference the old two-radio method widgets."""
    from metabwatch.gui.app import MetabWatchApp

    try:
        root = tk.Tk()
    except tk.TclError as exc:  # pragma: no cover - no display
        pytest.skip(f"Tk not available: {exc}")
    root.withdraw()
    try:
        app = MetabWatchApp(root)
        assert len(app.method_buttons) == len(METHOD_KEYS)
        keys = [str(button.cget("value")) for button in app.method_buttons]
        assert list(METHOD_KEYS) == keys
        assert str(app.polarity_auto.cget("value")) == "auto"
        assert str(app.polarity_positive.cget("value")) == "positive"
        assert str(app.polarity_negative.cget("value")) == "negative"
        app._update_source_enabled()
        app._set_running_ui(True)
        app._set_running_ui(False)
    finally:
        root.destroy()
