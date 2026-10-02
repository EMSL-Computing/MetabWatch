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
        label = ttk.Label(root, text="Run filter")
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


def test_hover_tooltip_shown_label_has_dark_text() -> None:
    """Pale-yellow tip must not use macOS systemTextColor (white in dark mode)."""
    from metabwatch.gui.tooltip import HoverTooltip

    root = _tk_root()
    try:
        label = ttk.Label(root, text="Run filter")
        label.pack()
        root.update_idletasks()
        tip = HoverTooltip(
            label, "Optional. Only process files whose name contains this text."
        )
        tip._show()
        root.update_idletasks()
        assert tip._tip is not None
        child = tip._tip.winfo_children()[0]
        assert child.cget("text").startswith("Optional.")
        r, g, b = child.winfo_rgb(str(child.cget("foreground")))
        assert r < 20000 and g < 20000 and b < 20000, (
            child.cget("foreground"),
            r,
            g,
            b,
        )
        tip._hide()
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
        assert str(app.project_id_label.cget("text")) == "Run filter"
        texts = _tooltip_texts(app)
        assert "Choose packaged method shortcuts, or a config file you already have." in texts
        assert any(t.startswith("Run filter.") for t in texts)
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
        assert str(dialog.project_id_label.cget("text")) == "Run filter"
        texts = _tooltip_texts(dialog)
        assert "Folder of Thermo `.raw` files. Copied into the new JSON." in texts
        assert any(t.startswith("Run filter.") for t in texts)
        assert "How close a peak's mass must be to a target (parts per million)." in texts
        assert any("Parent folder" in t for t in texts)
        assert any("numbered name" in t for t in texts)
        assert any("largest peaks" in t for t in texts)
        assert any("Only process files whose name contains this text" in t for t in texts)
        assert any("Auto locks from the first successful file" in t for t in texts)
        assert str(dialog.polarity_auto.cget("value")) == "auto"
        assert str(dialog.polarity_positive.cget("value")) == "positive"
        assert str(dialog.polarity_negative.cget("value")) == "negative"
        dialog.destroy()
    finally:
        root.destroy()


def test_stamp_log_line_time_only_within_same_day() -> None:
    from datetime import date, datetime

    from metabwatch.gui.app import _stamp_log_line

    now = datetime(2026, 10, 1, 14, 3, 22)
    line, last = _stamp_log_line("hello", now, date(2026, 10, 1))
    assert line == "14:03:22 hello"
    assert last == date(2026, 10, 1)


def test_stamp_log_line_includes_date_on_first_line_rollover_and_separator() -> None:
    from datetime import date, datetime

    from metabwatch.gui.app import _stamp_log_line

    now = datetime(2026, 10, 2, 0, 0, 5)
    assert _stamp_log_line("first", now, None)[0] == "2026-10-02 00:00:05 first"
    assert _stamp_log_line("next day", now, date(2026, 10, 1))[0] == (
        "2026-10-02 00:00:05 next day"
    )
    assert _stamp_log_line("---", now, date(2026, 10, 2), separator=True)[0] == (
        "2026-10-02 00:00:05 ---"
    )


def test_save_log_writes_panel_text(tmp_path, monkeypatch) -> None:
    from metabwatch.gui.app import MetabWatchApp

    root = _tk_root()
    dest = tmp_path / "out" / "metabwatch-log.txt"
    seen: dict[str, object] = {}

    def _ask(**kwargs: object) -> str:
        seen.update(kwargs)
        dest.parent.mkdir()
        return str(dest)

    monkeypatch.setattr("metabwatch.gui.app.filedialog.asksaveasfilename", _ask)
    try:
        app = MetabWatchApp(root, log_timestamps=False)
        app.output_var.set(str(tmp_path))
        app._append_log("first")
        app._append_log("second")
        app._set_running_ui(True)
        assert str(app.save_log_btn.cget("state")) == tk.NORMAL
        app._save_log()
        assert seen["initialdir"] == str(tmp_path)
        assert seen["initialfile"] == "metabwatch-log.txt"
        assert dest.read_text(encoding="utf-8") == "first\nsecond\n"
    finally:
        root.destroy()


def test_save_log_cancel_writes_nothing(tmp_path, monkeypatch) -> None:
    from metabwatch.gui.app import MetabWatchApp

    root = _tk_root()
    monkeypatch.setattr(
        "metabwatch.gui.app.filedialog.asksaveasfilename", lambda **_kwargs: ""
    )
    try:
        app = MetabWatchApp(root, log_timestamps=False)
        app._append_log("kept in the panel")
        app._save_log()
        assert list(tmp_path.iterdir()) == []
        assert "kept in the panel" in app.log.get("1.0", "end-1c")
    finally:
        root.destroy()


def test_save_log_reports_write_errors(tmp_path, monkeypatch) -> None:
    from metabwatch.gui.app import MetabWatchApp

    root = _tk_root()
    errors: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "metabwatch.gui.app.filedialog.asksaveasfilename",
        lambda **_kwargs: str(tmp_path / "missing" / "log.txt"),
    )
    monkeypatch.setattr(
        "metabwatch.gui.app.messagebox.showerror",
        lambda title, message: errors.append((title, message)),
    )
    try:
        app = MetabWatchApp(root, log_timestamps=False)
        app._append_log("line")
        app._save_log()
        assert errors and errors[0][0] == "Save log"
        assert not (tmp_path / "missing" / "log.txt").exists()
    finally:
        root.destroy()


@pytest.mark.parametrize("enabled", [True, False])
def test_gui_log_timestamps_toggle(enabled: bool) -> None:
    import re

    from metabwatch.gui.app import MetabWatchApp

    root = _tk_root()
    try:
        app = MetabWatchApp(root, log_timestamps=enabled)
        app._append_log("first")
        app._append_log("second")
        lines = app.log.get("1.0", "end-1c").splitlines()
        if enabled:
            assert re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} first", lines[0])
            assert re.fullmatch(r"\d{2}:\d{2}:\d{2} second", lines[1])
        else:
            assert lines == ["first", "second"]
    finally:
        root.destroy()
