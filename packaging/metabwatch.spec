# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec: single-file, windowed MetabWatch GUI for Windows.

Build with ``packaging/build.ps1`` (see docs/BUILDING.md). Run directly with:

    pyinstaller packaging/metabwatch.spec --noconfirm

Requires metabwatch to be *installed* (non-editable) in the build venv so its
package data and dist-info metadata can be collected.
"""

import importlib.util
import tomllib
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, copy_metadata
from PyInstaller.utils.win32.versioninfo import (
    FixedFileInfo,
    StringFileInfo,
    StringStruct,
    StringTable,
    VarFileInfo,
    VarStruct,
    VSVersionInfo,
)

HERE = Path(SPECPATH)  # noqa: F821 - injected by PyInstaller
ROOT = HERE.parent

VERSION = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
APP_NAME = f"MetabWatch-{VERSION}"

# ---------------------------------------------------------------------------
# Data files
# ---------------------------------------------------------------------------
datas = []
# Presets (*.toml/*.csv), starter README, dashboard template, vendored Plotly.js.
datas += collect_data_files("metabwatch")
# dist-info so metabwatch.get_version() reads the real version.
datas += copy_metadata("metabwatch")
# Thermo RawFileReader .NET assemblies shipped by CoreMS as top-level
# ``ext_lib``. CoreMS locates them relative to the corems package
# (<root>/ext_lib/dotnet), which matches their layout under _MEIPASS.
# The license file is kept: Thermo's redistribution terms require it.
datas += collect_data_files("ext_lib", excludes=["**/*.xml", "**/__pycache__/*"])

# ---------------------------------------------------------------------------
# Native libraries loaded by path (invisible to import analysis)
# ---------------------------------------------------------------------------
binaries = []
# IsoSpecPy (CoreMS isotopologue calc) cffi-dlopens IsoSpecCppPy.dll from
# <site-packages>/bin; IsoSpecPy searches <package>/../bin, i.e. _MEIPASS/bin.
_isospec_bin = Path(importlib.util.find_spec("IsoSpecPy").origin).parent.parent / "bin"
binaries += [(str(p), "bin") for p in _isospec_bin.glob("IsoSpecCppPy*.dll")]
if not binaries:
    raise SystemExit(f"IsoSpecCppPy*.dll not found under {_isospec_bin}")

# ---------------------------------------------------------------------------
# Excludes: packages installed with CoreMS but never imported on MetabWatch's
# code paths (verified with `python -X importtime`), plus dev/test tooling.
# If the self-test or a real run fails with ModuleNotFoundError, remove the
# module from this list.
# ---------------------------------------------------------------------------
EXCLUDES = [
    # CoreMS optional I/O backends not used for Thermo .raw LC-MS
    "h5py",
    "netCDF4",
    "cftime",
    "pymzml",
    "psycopg2",
    "openpyxl",
    "persim",
    "ms_entropy",
    # Build / dev tooling
    "Cython",
    "cython",
    "pyximport",
    "pip",
    "setuptools",
    "pkg_resources",
    "IPython",
    "jupyter",
    "notebook",
    "pytest",
    "_pytest",
    # Alternate matplotlib GUI backends (MetabWatch forces Agg)
    "PyQt5",
    "PyQt6",
    "PySide2",
    "PySide6",
    "wx",
    "gi",
]

a = Analysis(  # noqa: F821
    [str(HERE / "metabwatch_gui.py")],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUDES,
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)  # noqa: F821

# ---------------------------------------------------------------------------
# Windows version resource (Explorer > Properties > Details)
# ---------------------------------------------------------------------------
_parts = [int(p) for p in VERSION.split(".")[:3]] + [0]
_vtuple = tuple((_parts + [0, 0, 0, 0])[:4])
version_info = VSVersionInfo(
    ffi=FixedFileInfo(filevers=_vtuple, prodvers=_vtuple),
    kids=[
        StringFileInfo(
            [
                StringTable(
                    "040904B0",
                    [
                        StringStruct("CompanyName", "Pacific Northwest National Laboratory"),
                        StringStruct("FileDescription", "MetabWatch LC-MS QC watcher"),
                        StringStruct("FileVersion", VERSION),
                        StringStruct("InternalName", "MetabWatch"),
                        StringStruct("OriginalFilename", f"{APP_NAME}.exe"),
                        StringStruct("ProductName", "MetabWatch"),
                        StringStruct("ProductVersion", VERSION),
                    ],
                )
            ]
        ),
        VarFileInfo([VarStruct("Translation", [1033, 1200])]),
    ],
)

_icon = HERE / "metabwatch.ico"

exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # UPX corrupts .NET/native DLLs and raises AV false positives
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    version=version_info,
    icon=str(_icon) if _icon.is_file() else None,
)
