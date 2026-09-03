"""Delayed hover notes for Tk widgets. No extra dependencies."""

from __future__ import annotations

import tkinter as tk

# Plain-language copy for lab users (not JSON keys).
MAIN_HOVER = {
    "config_source": (
        "Choose packaged method shortcuts, or a config file you already have."
    ),
    "preset_shortcuts": (
        "Built-in LC method + targeted/untargeted. Input/output folders are set here."
    ),
    "custom_json": "Run from a config file. Paths come from that file.",
    "method_preset": "Packaged chromatography / CoreMS / QC settings.",
    "search": (
        "Targeted matches the compound list; untargeted builds a list "
        "from the first matching sample."
    ),
    "project_id": (
        "Optional. Only process files whose name contains this text "
        "(not case-sensitive). Leave empty to keep the usual sample filter "
        "(`QC_Metab_` or `Pool`) with no extra restriction."
    ),
    "polarity": (
        "Auto locks from the first successful file; Positive/Negative lock "
        "before the first sample. One polarity per output folder."
    ),
    "input_folder": "Folder of Thermo `.raw` files.",
    "output_folder": (
        "Where the dashboard, CSVs, and manifest are written."
    ),
    "config_file": "Path to a pipeline JSON (same as CLI `--config`).",
    "watch": "Keep looking for new `.raw` files until Stop.",
    "process_once": "Process what is already there, then exit.",
    "force_reprocess": (
        "Run again even if the manifest says the file was already done."
    ),
    "create_custom_config": (
        "Make a new folder with a JSON, RP CoreMS settings, a README, "
        "and (targeted) a blank compound list. Does not overwrite an existing folder."
    ),
}

STARTER_HOVER = {
    "input_folder": "Folder of Thermo `.raw` files. Copied into the new JSON.",
    "output_folder": "Where the dashboard, CSVs, and manifest will be written.",
    "search_mode": MAIN_HOVER["search"],
    "mz": "How close a peak's mass must be to a target (parts per million).",
    "rt": "How close retention time must be to a target.",
    "min_area": "Ignore peaks smaller than this.",
    "sample_regex": "Only process files whose name matches this pattern.",
    "top_n": (
        "How many of the largest peaks to keep when building the untargeted list."
    ),
    "save_in": "Parent folder where the new config folder will be created.",
    "folder_name": (
        "Name of the new folder. If it already exists, you will be offered "
        "a numbered name instead."
    ),
}


def add_hover(
    store: list[HoverTooltip],
    *widgets: tk.Misc,
    text: str,
) -> None:
    """Attach the same delayed note to one or more widgets; keep refs in store."""
    for widget in widgets:
        store.append(HoverTooltip(widget, text))


class HoverTooltip:
    """Show a delayed hover note near a widget."""

    def __init__(self, widget: tk.Misc, text: str, *, delay_ms: int = 500) -> None:
        self.widget = widget
        self.text = text
        self.delay_ms = delay_ms
        self._after_id: str | None = None
        self._tip: tk.Toplevel | None = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")

    def _schedule(self, _event: object | None = None) -> None:
        self._cancel()
        self._after_id = self.widget.after(self.delay_ms, self._show)

    def _cancel(self) -> None:
        if self._after_id is not None:
            try:
                self.widget.after_cancel(self._after_id)
            except tk.TclError:
                pass
            self._after_id = None

    def _show(self) -> None:
        self._after_id = None
        if self._tip is not None:
            return
        try:
            x = self.widget.winfo_rootx() + 12
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
        except tk.TclError:
            return
        tip = tk.Toplevel(self.widget)
        tip.wm_overrideredirect(True)
        try:
            tip.wm_attributes("-topmost", True)
        except tk.TclError:
            pass
        tip.wm_geometry(f"+{x}+{y}")
        tk.Label(
            tip,
            text=self.text,
            justify=tk.LEFT,
            background="#ffffe0",
            relief=tk.SOLID,
            borderwidth=1,
            wraplength=360,
            padx=6,
            pady=4,
        ).pack()
        self._tip = tip

    def _hide(self, _event: object | None = None) -> None:
        self._cancel()
        if self._tip is not None:
            try:
                self._tip.destroy()
            except tk.TclError:
                pass
            self._tip = None
