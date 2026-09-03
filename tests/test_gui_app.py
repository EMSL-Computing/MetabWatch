"""Smoke tests for the Tkinter GUI shell."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

import pytest

from metabwatch.presets import METHOD_KEYS, PRESET_SPECS


def _tk_root() -> tk.Tk:
    try:
        root = tk.Tk()
    except tk.TclError as exc:  # pragma: no cover - no display
        pytest.skip(f"Tk not available: {exc}")
    root.withdraw()
    return root


def _tooltip_texts(owner) -> set[str]:
    return {tip.text for tip in owner._tooltips}


def test_hover_tooltip_can_be_constructed() -> None:
    """Delayed hover helper exists and binds without showing a window."""
    from metabwatch.gui.tooltip import HoverTooltip

    root = _tk_root()
    try:
        label = ttk.Label(root, text="Project ID")
        tip = HoverTooltip(label, "Optional. Only process files whose name contains this text.")
        assert tip.delay_ms == 500
        assert tip._tip is None
        tip._schedule()
        assert tip._after_id is not None
        tip._hide()
        assert tip._after_id is None
        assert tip._tip is None
    finally:
        root.destroy()


def test_gui_app_builds_with_method_dropdown() -> None:
    """Method preset is a combobox of all packaged presets, not a stack of radios."""
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


def test_gui_app_attaches_hover_notes_to_option_labels() -> None:
    """Main-window option labels keep delayed hover copy (not GC'd)."""
    from metabwatch.gui.app import MetabWatchApp

    root = _tk_root()
    try:
        app = MetabWatchApp(root)
        texts = _tooltip_texts(app)
        assert "Choose packaged method shortcuts, or a config file you already have." in texts
        assert "Packaged chromatography / CoreMS / QC settings." in texts
        assert any("Only process files whose name contains this text" in t for t in texts)
        assert "Folder of Thermo `.raw` files." in texts
        assert "Path to a pipeline JSON (same as CLI `--config`)." in texts
        assert "Keep looking for new `.raw` files until Stop." in texts
        assert any("new folder with a JSON" in t for t in texts)
        assert app._tooltips, "tooltip objects must be stored on the app"
    finally:
        root.destroy()


def test_starter_dialog_attaches_hover_notes() -> None:
    """Create-custom-config fields have the same style of delayed hover notes."""
    from metabwatch.gui.app import StarterConfigDialog

    root = _tk_root()
    try:
        dialog = StarterConfigDialog(root, on_saved=lambda _result: None)
        texts = _tooltip_texts(dialog)
        assert "Folder of Thermo `.raw` files. Copied into the new JSON." in texts
        assert "How close a peak's mass must be to a target (parts per million)." in texts
        assert any("Parent folder" in t for t in texts)
        assert any("numbered name" in t for t in texts)
        assert any("largest peaks" in t for t in texts)
        dialog.destroy()
    finally:
        root.destroy()
