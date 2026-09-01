"""Tkinter GUI for MetabWatch (Windows-first)."""

from __future__ import annotations

import os
import queue
import subprocess
import sys
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk

from metabwatch.gui.runner import PipelineRunner, RunnerState
from metabwatch.gui.validation import GuiRunRequest, preset_summary_text
from metabwatch.presets import METHOD_KEYS, PRESET_SPECS


class MetabWatchApp(ttk.Frame):
    """Main application frame."""

    def __init__(self, master: tk.Tk, *, config_path: str | None = None) -> None:
        super().__init__(master, padding=12)
        self.master = master
        self.runner = PipelineRunner()

        self.source_var = tk.StringVar(value="preset")
        self.method_var = tk.StringVar(value="hilic_metab_pnnl")
        self.search_var = tk.StringVar(value="targeted")
        self.polarity_var = tk.StringVar(value="auto")
        self.project_id_var = tk.StringVar()
        self.input_var = tk.StringVar()
        self.output_var = tk.StringVar()
        self.config_var = tk.StringVar()
        self.run_mode_var = tk.StringVar(value="watch")
        self.force_var = tk.BooleanVar(value=False)
        self.status_var = tk.StringVar(value="Status: Idle")
        self.summary_var = tk.StringVar()

        self._build()
        self._bind_traces()
        self._update_source_enabled()
        self._update_summary()
        self._set_running_ui(False)
        if config_path:
            self._prefill_config(config_path)
        self.after(150, self._drain_log)

    def _prefill_config(self, config_path: str) -> None:
        """Select Custom JSON and set the config path (launcher / CLI prefill)."""
        path = str(Path(config_path).expanduser().resolve())
        self.source_var.set("json")
        self.config_var.set(path)
        self._update_source_enabled()
        self.status_var.set(f"Status: Idle (config: {Path(path).name})")

    def _build(self) -> None:
        self.grid(sticky="nsew")
        self.master.columnconfigure(0, weight=1)
        self.master.rowconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)

        row = 0

        # Config source
        ttk.Label(self, text="Config source").grid(row=row, column=0, sticky="w", pady=2)
        src_frame = ttk.Frame(self)
        src_frame.grid(row=row, column=1, sticky="w", pady=2)
        self.source_preset_rb = ttk.Radiobutton(
            src_frame,
            text="Preset shortcuts",
            variable=self.source_var,
            value="preset",
            command=self._update_source_enabled,
        )
        self.source_preset_rb.pack(side=tk.LEFT, padx=(0, 12))
        self.source_json_rb = ttk.Radiobutton(
            src_frame,
            text="Custom JSON",
            variable=self.source_var,
            value="json",
            command=self._update_source_enabled,
        )
        self.source_json_rb.pack(side=tk.LEFT)
        row += 1

        # Preset section
        self.preset_frame = ttk.LabelFrame(self, text="Preset", padding=8)
        self.preset_frame.grid(row=row, column=0, columnspan=3, sticky="ew", pady=6)
        self.preset_frame.columnconfigure(1, weight=1)
        prow = 0

        ttk.Label(self.preset_frame, text="LC Method").grid(
            row=prow, column=0, sticky="w", pady=2
        )
        method_frame = ttk.Frame(self.preset_frame)
        method_frame.grid(row=prow, column=1, sticky="w", pady=2)
        self.method_buttons: list[ttk.Radiobutton] = []
        for key in METHOD_KEYS:
            button = ttk.Radiobutton(
                method_frame,
                text=PRESET_SPECS[key]["display_name"],
                variable=self.method_var,
                value=key,
                command=self._update_summary,
            )
            button.pack(side=tk.TOP, anchor="w")
            self.method_buttons.append(button)
        prow += 1

        ttk.Label(self.preset_frame, text="Search").grid(
            row=prow, column=0, sticky="w", pady=2
        )
        search_frame = ttk.Frame(self.preset_frame)
        search_frame.grid(row=prow, column=1, sticky="w", pady=2)
        self.search_targeted = ttk.Radiobutton(
            search_frame,
            text="Targeted",
            variable=self.search_var,
            value="targeted",
            command=self._update_summary,
        )
        self.search_targeted.pack(side=tk.LEFT, padx=(0, 12))
        self.search_untargeted = ttk.Radiobutton(
            search_frame,
            text="Untargeted",
            variable=self.search_var,
            value="untargeted",
            command=self._update_summary,
        )
        self.search_untargeted.pack(side=tk.LEFT)
        prow += 1

        ttk.Label(self.preset_frame, text="Project ID").grid(
            row=prow, column=0, sticky="w", pady=2
        )
        self.project_id_entry = ttk.Entry(
            self.preset_frame, textvariable=self.project_id_var
        )
        self.project_id_entry.grid(row=prow, column=1, sticky="ew", pady=2)
        prow += 1

        ttk.Label(self.preset_frame, text="Polarity").grid(
            row=prow, column=0, sticky="w", pady=2
        )
        polarity_frame = ttk.Frame(self.preset_frame)
        polarity_frame.grid(row=prow, column=1, sticky="w", pady=2)
        self.polarity_auto = ttk.Radiobutton(
            polarity_frame,
            text="Auto",
            variable=self.polarity_var,
            value="auto",
        )
        self.polarity_auto.pack(side=tk.LEFT, padx=(0, 12))
        self.polarity_positive = ttk.Radiobutton(
            polarity_frame,
            text="Positive",
            variable=self.polarity_var,
            value="positive",
        )
        self.polarity_positive.pack(side=tk.LEFT, padx=(0, 12))
        self.polarity_negative = ttk.Radiobutton(
            polarity_frame,
            text="Negative",
            variable=self.polarity_var,
            value="negative",
        )
        self.polarity_negative.pack(side=tk.LEFT)
        prow += 1

        ttk.Label(self.preset_frame, text="Input folder").grid(
            row=prow, column=0, sticky="w", pady=2
        )
        self.input_entry = ttk.Entry(self.preset_frame, textvariable=self.input_var)
        self.input_entry.grid(row=prow, column=1, sticky="ew", pady=2, padx=(0, 6))
        self.input_browse = ttk.Button(
            self.preset_frame, text="Browse…", command=self._browse_input
        )
        self.input_browse.grid(row=prow, column=2, pady=2)
        prow += 1

        ttk.Label(self.preset_frame, text="Output folder").grid(
            row=prow, column=0, sticky="w", pady=2
        )
        self.output_entry = ttk.Entry(self.preset_frame, textvariable=self.output_var)
        self.output_entry.grid(row=prow, column=1, sticky="ew", pady=2, padx=(0, 6))
        self.output_browse = ttk.Button(
            self.preset_frame, text="Browse…", command=self._browse_output
        )
        self.output_browse.grid(row=prow, column=2, pady=2)
        prow += 1

        self.summary_label = ttk.Label(
            self.preset_frame,
            textvariable=self.summary_var,
            foreground="#444444",
            wraplength=640,
        )
        self.summary_label.grid(row=prow, column=0, columnspan=3, sticky="w", pady=(4, 0))
        row += 1

        # JSON section
        self.json_frame = ttk.LabelFrame(self, text="Custom JSON", padding=8)
        self.json_frame.grid(row=row, column=0, columnspan=3, sticky="ew", pady=6)
        self.json_frame.columnconfigure(1, weight=1)
        ttk.Label(self.json_frame, text="Config file").grid(
            row=0, column=0, sticky="w", pady=2
        )
        self.config_entry = ttk.Entry(self.json_frame, textvariable=self.config_var)
        self.config_entry.grid(row=0, column=1, sticky="ew", pady=2, padx=(0, 6))
        self.config_browse = ttk.Button(
            self.json_frame, text="Browse…", command=self._browse_config
        )
        self.config_browse.grid(row=0, column=2, pady=2)
        ttk.Label(
            self.json_frame,
            text="Same schema as CLI --config (simplified or legacy). "
            "Input/output paths come from the JSON.",
            foreground="#444444",
            wraplength=640,
        ).grid(row=1, column=0, columnspan=3, sticky="w", pady=(4, 0))
        row += 1

        # Run options
        run_frame = ttk.LabelFrame(self, text="Run options", padding=8)
        run_frame.grid(row=row, column=0, columnspan=3, sticky="ew", pady=6)
        mode_frame = ttk.Frame(run_frame)
        mode_frame.pack(anchor="w")
        ttk.Radiobutton(
            mode_frame,
            text="Watch continuously",
            variable=self.run_mode_var,
            value="watch",
        ).pack(side=tk.LEFT, padx=(0, 12))
        ttk.Radiobutton(
            mode_frame,
            text="Process once",
            variable=self.run_mode_var,
            value="once",
        ).pack(side=tk.LEFT)
        ttk.Checkbutton(
            run_frame,
            text="Force reprocess",
            variable=self.force_var,
        ).pack(anchor="w", pady=(6, 0))
        row += 1

        # Buttons
        btn_frame = ttk.Frame(self)
        btn_frame.grid(row=row, column=0, columnspan=3, sticky="w", pady=6)
        self.start_btn = ttk.Button(btn_frame, text="Start", command=self._on_start)
        self.start_btn.pack(side=tk.LEFT, padx=(0, 6))
        self.stop_btn = ttk.Button(btn_frame, text="Stop", command=self._on_stop)
        self.stop_btn.pack(side=tk.LEFT, padx=(0, 6))
        self.dash_btn = ttk.Button(
            btn_frame, text="Open dashboard", command=self._open_dashboard
        )
        self.dash_btn.pack(side=tk.LEFT, padx=(0, 6))
        self.out_btn = ttk.Button(
            btn_frame, text="Open output", command=self._open_output
        )
        self.out_btn.pack(side=tk.LEFT)
        row += 1

        ttk.Label(self, textvariable=self.status_var).grid(
            row=row, column=0, columnspan=3, sticky="w", pady=(0, 4)
        )
        row += 1

        # Log
        log_frame = ttk.LabelFrame(self, text="Log", padding=4)
        log_frame.grid(row=row, column=0, columnspan=3, sticky="nsew", pady=4)
        self.rowconfigure(row, weight=1)
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        self.log = scrolledtext.ScrolledText(
            log_frame, height=16, wrap=tk.WORD, state=tk.DISABLED, font=("Consolas", 9)
        )
        self.log.grid(row=0, column=0, sticky="nsew")

    def _bind_traces(self) -> None:
        self.method_var.trace_add("write", lambda *_: self._update_summary())
        self.search_var.trace_add("write", lambda *_: self._update_summary())

    def _update_summary(self) -> None:
        self.summary_var.set(
            preset_summary_text(self.method_var.get(), self.search_var.get())
        )

    def _update_source_enabled(self) -> None:
        preset = self.source_var.get() == "preset"
        preset_state = tk.NORMAL if preset else tk.DISABLED
        json_state = tk.DISABLED if preset else tk.NORMAL

        for widget in (
            *self.method_buttons,
            self.search_targeted,
            self.search_untargeted,
            self.project_id_entry,
            self.polarity_auto,
            self.polarity_positive,
            self.polarity_negative,
            self.input_entry,
            self.input_browse,
            self.output_entry,
            self.output_browse,
        ):
            widget.configure(state=preset_state)

        self.config_entry.configure(state=json_state)
        self.config_browse.configure(state=json_state)

    def _browse_input(self) -> None:
        path = filedialog.askdirectory(title="Select input folder (Thermo .raw files)")
        if path:
            self.input_var.set(path)

    def _browse_output(self) -> None:
        path = filedialog.askdirectory(title="Select output folder")
        if path:
            self.output_var.set(path)

    def _browse_config(self) -> None:
        path = filedialog.askopenfilename(
            title="Select pipeline config JSON",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        if path:
            self.config_var.set(path)

    def _build_request(self) -> GuiRunRequest:
        return GuiRunRequest(
            source="preset" if self.source_var.get() == "preset" else "json",
            method=self.method_var.get(),
            search=self.search_var.get(),
            polarity=self.polarity_var.get(),
            project_id=self.project_id_var.get(),
            input_folder=self.input_var.get(),
            output_folder=self.output_var.get(),
            config_path=self.config_var.get(),
            once=self.run_mode_var.get() == "once",
            force_reprocess=bool(self.force_var.get()),
        )

    def _on_start(self) -> None:
        if self.runner.is_running:
            messagebox.showinfo("MetabWatch", "A run is already in progress.")
            return
        request = self._build_request()
        try:
            self.runner.start(request, on_finished=self._on_finished)
        except ValueError as exc:
            messagebox.showerror("Invalid settings", str(exc))
            return
        except Exception as exc:  # pragma: no cover
            messagebox.showerror("Failed to start", str(exc))
            return

        self._append_log("---")
        mode = "once" if request.once else "watch"
        src = "preset" if request.source == "preset" else "JSON config"
        self.status_var.set(f"Status: Running ({src}, {mode})…")
        self._set_running_ui(True)

    def _on_stop(self) -> None:
        if not self.runner.is_running:
            return
        self.runner.request_stop()
        self.status_var.set("Status: Stopping (after current file)…")

    def _on_finished(self, state: RunnerState) -> None:
        # Called from worker thread — schedule UI update on main thread.
        self.after(0, lambda: self._finish_ui(state))

    def _finish_ui(self, state: RunnerState) -> None:
        self._set_running_ui(False)
        if state.error:
            self.status_var.set(f"Status: Error — {state.error}")
        elif state.exit_code == 0:
            self.status_var.set("Status: Done")
        else:
            self.status_var.set(f"Status: Finished with errors (exit {state.exit_code})")

    def _set_running_ui(self, running: bool) -> None:
        self.start_btn.configure(state=tk.DISABLED if running else tk.NORMAL)
        self.stop_btn.configure(state=tk.NORMAL if running else tk.DISABLED)
        # Disable source switching while running
        src_state = tk.DISABLED if running else tk.NORMAL
        self.source_preset_rb.configure(state=src_state)
        self.source_json_rb.configure(state=src_state)
        if running:
            # Lock form fields for the active source
            for widget in (
                *self.method_buttons,
                self.search_targeted,
                self.search_untargeted,
                self.project_id_entry,
                self.polarity_auto,
                self.polarity_positive,
                self.polarity_negative,
                self.input_entry,
                self.input_browse,
                self.output_entry,
                self.output_browse,
                self.config_entry,
                self.config_browse,
            ):
                widget.configure(state=tk.DISABLED)
        else:
            self._update_source_enabled()

    def _drain_log(self) -> None:
        try:
            while True:
                line = self.runner.log_queue.get_nowait()
                self._append_log(line)
        except queue.Empty:
            pass
        self.after(150, self._drain_log)

    def _append_log(self, line: str) -> None:
        self.log.configure(state=tk.NORMAL)
        self.log.insert(tk.END, line + "\n")
        self.log.see(tk.END)
        self.log.configure(state=tk.DISABLED)

    def _open_dashboard(self) -> None:
        path = self.runner.dashboard_path()
        if path is None:
            # Try resolve from form without running
            try:
                cfg = self.runner.state.config
                if cfg is None:
                    from metabwatch.gui.validation import resolve_config

                    cfg = resolve_config(self._build_request())
                path = cfg.synthesizer.html_output
            except Exception as exc:
                messagebox.showerror("Open dashboard", str(exc))
                return
        if not path.is_file():
            # Write the same waiting page used at pipeline start (if output is known).
            try:
                from metabwatch.synthesis.synthesizer import HTMLSynthesizer

                cfg = self.runner.state.config
                if cfg is None:
                    from metabwatch.gui.validation import resolve_config

                    cfg = resolve_config(self._build_request())
                HTMLSynthesizer(
                    output_dirs=(cfg.synthesizer.output_dir,),
                    html_output=path,
                    mz_tolerance_ppm=cfg.synthesizer.mz_tolerance_ppm,
                    rt_tolerance=cfg.synthesizer.rt_tolerance,
                    untargeted_mode=(cfg.search_space.mode == "untargeted"),
                ).write_placeholder_if_missing()
            except Exception as exc:
                messagebox.showinfo(
                    "Open dashboard",
                    f"Dashboard not found yet:\n{path}\n\n{exc}",
                )
                return
            if not path.is_file():
                messagebox.showinfo(
                    "Open dashboard",
                    f"Dashboard not found yet:\n{path}\n\nRun the pipeline first.",
                )
                return
        webbrowser.open(path.resolve().as_uri())

    def _open_output(self) -> None:
        path = self.runner.output_dir()
        if path is None:
            try:
                from metabwatch.gui.validation import resolve_config

                cfg = resolve_config(self._build_request())
                path = cfg.processor.output_dir
            except Exception as exc:
                messagebox.showerror("Open output", str(exc))
                return
        if not path.exists():
            try:
                path.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                messagebox.showerror("Open output", str(exc))
                return
        self._reveal_path(path)

    @staticmethod
    def _reveal_path(path: Path) -> None:
        path = path.resolve()
        if sys.platform == "win32":
            os.startfile(str(path))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.run(["open", str(path)], check=False)
        else:
            subprocess.run(["xdg-open", str(path)], check=False)


def main(argv: list[str] | None = None) -> int:
    """Create the root window and run the Tk event loop."""
    import argparse

    from metabwatch import get_version

    parser = argparse.ArgumentParser(description="MetabWatch GUI")
    parser.add_argument(
        "--config",
        metavar="PATH",
        default=None,
        help="Pre-select Custom JSON mode with this pipeline config file",
    )
    args = parser.parse_args(argv)

    version = get_version()
    root = tk.Tk()
    root.title(f"MetabWatch {version}")
    root.minsize(720, 720)
    root.geometry("820x860")

    # Prefer native-ish ttk theme when available
    try:
        style = ttk.Style(root)
        if "vista" in style.theme_names():
            style.theme_use("vista")
        elif "clam" in style.theme_names():
            style.theme_use("clam")
    except tk.TclError:
        pass

    try:
        MetabWatchApp(root, config_path=args.config)
    except Exception as exc:  # pragma: no cover - UI error path
        messagebox.showerror(
            "MetabWatch failed to start",
            f"Could not open the MetabWatch window.\n\n{exc}\n\n"
            "If this is a frozen Windows build, ensure Visual C++ "
            "redistributables are installed and try again from a console "
            "to see full errors.",
        )
        return 1
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
