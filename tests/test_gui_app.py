"""Smoke tests for the Tkinter GUI shell."""

from __future__ import annotations

import tkinter as tk

import pytest

from metabwatch.presets import METHOD_KEYS, PRESET_SPECS


def test_gui_app_builds_with_method_dropdown() -> None:
    """LC Method is a combobox of all packaged presets, not a stack of radios."""
    from metabwatch.gui.app import MetabWatchApp

    try:
        root = tk.Tk()
    except tk.TclError as exc:  # pragma: no cover - no display
        pytest.skip(f"Tk not available: {exc}")
    root.withdraw()
    try:
        app = MetabWatchApp(root)
        labels = [PRESET_SPECS[key]["display_name"] for key in METHOD_KEYS]
        assert list(app.method_combo.cget("values")) == labels
        assert app.method_var.get() == METHOD_KEYS[0]
        assert app.method_name_var.get() == labels[0]
        app.method_name_var.set(labels[-1])
        app._on_method_selected()
        assert app.method_var.get() == METHOD_KEYS[-1]
        assert str(app.method_combo.cget("state")) == "readonly"
        app.source_var.set("json")
        app._update_source_enabled()
        assert str(app.method_combo.cget("state")) == "disabled"
        app.source_var.set("preset")
        app._update_source_enabled()
        assert str(app.method_combo.cget("state")) == "readonly"
        assert str(app.polarity_auto.cget("value")) == "auto"
        assert str(app.polarity_positive.cget("value")) == "positive"
        assert str(app.polarity_negative.cget("value")) == "negative"
        app._set_running_ui(True)
        assert str(app.method_combo.cget("state")) == "disabled"
        app._set_running_ui(False)
        assert str(app.method_combo.cget("state")) == "readonly"
    finally:
        root.destroy()
