"""Frozen-exe entry point for the MetabWatch GUI (PyInstaller).

Not part of the installed package. ``packaging/metabwatch.spec`` builds this
script into ``MetabWatch-X.Y.Z.exe``. Responsibilities beyond
``metabwatch.gui.main()``:

* ``multiprocessing.freeze_support()`` so any CoreMS worker pool re-enters
  here safely instead of relaunching the GUI.
* A windowed exe has no console (``sys.stdout``/``sys.stderr`` are ``None``),
  so stray ``print``/tqdm output from CoreMS would crash. Route both streams
  to a per-launch log under ``%LOCALAPPDATA%\\MetabWatch\\logs``.
* ``--self-test [REPORT]``: headless check that bundled modules, the Thermo
  .NET reader and package data all load. Used by ``packaging/build.ps1``.
"""

from __future__ import annotations

import faulthandler
import multiprocessing
import os
import sys
import traceback
from datetime import datetime
from pathlib import Path

KEEP_LOGS = 20


def _log_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home())
    path = Path(base) / "MetabWatch" / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _prune_logs(log_dir: Path) -> None:
    logs = sorted(log_dir.glob("metabwatch-*.log"), key=lambda p: p.stat().st_mtime)
    for old in logs[:-KEEP_LOGS]:
        try:
            old.unlink()
        except OSError:
            pass


def _redirect_missing_streams() -> Path | None:
    """Point ``None`` std streams at a log file; return its path (or None)."""
    if sys.stdout is not None and sys.stderr is not None:
        return None
    try:
        log_dir = _log_dir()
        _prune_logs(log_dir)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        log_path = log_dir / f"metabwatch-{stamp}-{os.getpid()}.log"
        stream = open(log_path, "a", encoding="utf-8", buffering=1)  # noqa: SIM115
    except OSError:
        stream, log_path = open(os.devnull, "w"), None  # noqa: SIM115
    if sys.stdout is None:
        sys.stdout = stream
    if sys.stderr is None:
        sys.stderr = stream
    try:
        faulthandler.enable(stream)
    except (OSError, ValueError):
        pass
    return log_path


def _install_excepthook(log_path: Path | None) -> None:
    def hook(exc_type, exc, tb):  # type: ignore[no-untyped-def]
        text = "".join(traceback.format_exception(exc_type, exc, tb))
        print(text, file=sys.stderr, flush=True)
        try:
            from tkinter import messagebox

            where = f"\n\nDetails were written to:\n{log_path}" if log_path else ""
            messagebox.showerror("MetabWatch error", f"{exc}{where}")
        except Exception:
            pass

    sys.excepthook = hook


def _self_test(report_path: Path) -> int:
    """Exercise imports and bundled data without opening a window."""
    import importlib
    import pkgutil
    import tempfile

    os.environ.setdefault("MPLBACKEND", "Agg")
    results: list[tuple[str, bool, str]] = []

    def check(name: str, fn) -> None:  # type: ignore[no-untyped-def]
        try:
            detail = fn() or ""
            results.append((name, True, str(detail)))
        except BaseException as exc:  # noqa: BLE001 - report everything
            results.append((name, False, f"{type(exc).__name__}: {exc}"))

    def import_all_metabwatch() -> str:
        import metabwatch

        names = [m.name for m in pkgutil.walk_packages(metabwatch.__path__, "metabwatch.")]
        for name in names:
            importlib.import_module(name)
        return f"{len(names)} modules, version {metabwatch.get_version()}"

    def thermo_reader() -> str:
        from corems.mass_spectra.input import rawFileReader  # noqa: F401  (loads CLR + DLLs)
        import System

        loaded = [
            a.GetName().Name
            for a in System.AppDomain.CurrentDomain.GetAssemblies()
            if a.GetName().Name.startswith("ThermoFisher.CommonCore")
        ]
        if "ThermoFisher.CommonCore.RawFileReader" not in loaded:
            raise RuntimeError(f"Thermo RawFileReader assembly not loaded: {loaded}")
        return ", ".join(sorted(loaded))

    def presets() -> str:
        from metabwatch.presets import METHOD_KEYS, build_pipeline_config

        with tempfile.TemporaryDirectory() as tmp:
            for method in METHOD_KEYS:
                for search in ("targeted", "untargeted"):
                    build_pipeline_config(method, search, tmp, tmp)
        return f"{len(METHOD_KEYS)} methods x 2 searches"

    def starter_readme() -> str:
        from metabwatch.gui.starter import starter_readme_template_path

        return str(starter_readme_template_path())

    def plotly_asset() -> str:
        from metabwatch.synthesis import synthesizer

        path = synthesizer._PLOTLY_PACKAGE_PATH
        if not path.is_file():
            raise FileNotFoundError(path)
        return f"{path.name} ({path.stat().st_size // 1024} KB)"

    def tk_runtime() -> str:
        import tkinter

        return f"Tcl/Tk {tkinter.TclVersion}"

    check("import metabwatch.*", import_all_metabwatch)
    check("Thermo .raw reader (.NET)", thermo_reader)
    check("preset assets", presets)
    check("starter README template", starter_readme)
    check("Plotly.js asset", plotly_asset)
    check("tkinter", tk_runtime)

    ok = all(passed for _, passed, _ in results)
    lines = [f"MetabWatch self-test: {'PASS' if ok else 'FAIL'}"]
    lines += [f"  [{'ok' if p else 'FAIL'}] {n}: {d}" for n, p, d in results]
    report = "\n".join(lines) + "\n"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8")
    print(report)
    return 0 if ok else 1


def main() -> int:
    multiprocessing.freeze_support()
    log_path = _redirect_missing_streams()
    _install_excepthook(log_path)

    argv = sys.argv[1:]
    if argv and argv[0] == "--self-test":
        report = Path(argv[1]) if len(argv) > 1 else _log_dir() / "self-test.txt"
        return _self_test(report)

    from metabwatch.gui import main as gui_main

    return gui_main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
