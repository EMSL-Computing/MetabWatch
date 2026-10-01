# Building the Windows exe

How maintainers build `MetabWatch-X.Y.Z.exe`. This is the single file that lab
PCs run. Lab PCs need **no** Python. Installing it on a PC is covered in
[INSTALL.md](INSTALL.md).

Build on Windows 10/11 only. The exe runs on Windows 10/11 x64.

## Prerequisites (build PC only)

- **64-bit Python 3.13** from [python.org](https://www.python.org/downloads/).
  Use the official installer, because it includes tkinter. The `py` launcher
  must find it (`py -3.13 --version`).
- A clone of this repo, checked out at the commit or tag you want to ship.
- Internet access to PyPI for the first build, **or** a wheelhouse folder
  (see [Offline build](#offline-build)).

## Build

From the repo root in PowerShell:

```powershell
.\packaging\build.ps1 -Clean
```

When it finishes you have:

| File | Purpose |
|------|---------|
| `dist\MetabWatch-X.Y.Z.exe` | The app. Copy it to lab PCs. |
| `dist\MetabWatch-X.Y.Z.exe.sha256` | Checksum to publish with it. |

`-Clean` recreates the build venv (`.venv-build\`) and PyInstaller's work
folder. Leave it off to reuse the venv, which makes rebuilds faster when
dependencies have not changed. If PowerShell blocks the script, run
`powershell -ExecutionPolicy Bypass -File .\packaging\build.ps1 -Clean`.

The version comes from `pyproject.toml`. Nothing else needs editing.

### What the script does

1. Creates `.venv-build\` and installs the pinned
   [`packaging/requirements-build.txt`](../packaging/requirements-build.txt).
2. Installs MetabWatch into that venv as a normal (non-editable) install.
3. Runs PyInstaller with [`packaging/metabwatch.spec`](../packaging/metabwatch.spec).
4. Runs the new exe with `--self-test` and stops with an error if the
   self-test fails.
5. Writes the SHA-256 file and prints the size.

### Self-test

`MetabWatch-X.Y.Z.exe --self-test [REPORT.txt]` runs without opening a window.
It checks that:

- every `metabwatch.*` module imports
- the Thermo RawFileReader .NET assemblies load through pythonnet
- every preset (method × search) builds from the bundled TOML/CSV files
- the starter README template and the vendored Plotly.js are present
- Tcl/Tk is present

The report goes to `REPORT.txt`. Without that argument it goes to
`%LOCALAPPDATA%\MetabWatch\logs\self-test.txt`. Exit code 0 means pass. Run it
on a new lab PC to confirm the exe works there.

## Size and speed (reference build)

Reference build: v0.4.0 on Windows 11, Python 3.13.

| | |
|-|-|
| Exe size | ~115 MB |
| Build time (venv already set up) | ~3.5 min |
| Startup to window | ~12 s, every launch |

Each time the exe starts it unpacks itself to `%TEMP%\_MEI*`, which is why
startup takes about 12 seconds. The folder is removed when the window closes
normally; a force-killed exe leaves it behind, and it is safe to delete.
Processing speed is the same as in a venv install.

## Files in `packaging/`

| File | What it is |
|------|------------|
| `build.ps1` | The one-command build. |
| `metabwatch.spec` | PyInstaller config: data files, excludes, version resource. |
| `metabwatch_gui.py` | Exe entry point. Handles logging (the exe has no console), `freeze_support`, and `--self-test`. |
| `requirements-build.txt` | Pinned versions of every package bundled into the exe, plus PyInstaller. |
| `metabwatch.ico` | *(optional)* If present, used as the exe icon. |

## Maintenance

### Normal feature work

Nothing to do. Changes under `src/` are picked up automatically. Package data
is collected from the installed package, so a new file only needs adding to
`[tool.setuptools.package-data]` in `pyproject.toml`, the same step a pip
install needs.

### Dependencies changed

If `pyproject.toml` dependencies change, or you deliberately upgrade a
package, refresh the lock:

```powershell
py -3.13 -m venv $env:TEMP\mw-lock
& $env:TEMP\mw-lock\Scripts\python.exe -m pip install .
& $env:TEMP\mw-lock\Scripts\python.exe -m pip freeze | Select-String -NotMatch '^metabwatch' 
```

Paste the output into the runtime section of
`packaging/requirements-build.txt`, keeping the header and the PyInstaller
pins. Also bump `pyinstaller` and `pyinstaller-hooks-contrib` if needed. Then
run `build.ps1 -Clean` and do a real-data test run (see the
[release checklist](RELEASING.md#checklist)).

### Excludes

`EXCLUDES` in `metabwatch.spec` drops packages that come with CoreMS but are
never imported on MetabWatch's code paths (h5py, netCDF4, pymzml, psycopg2,
openpyxl, ...). This keeps the exe smaller. If a future feature starts using
one of them, delete it from the list. To check what is really imported:

```powershell
.\.venv\Scripts\python.exe -X importtime packaging\metabwatch_gui.py --self-test 2>&1 | Select-String "metabwatch|corems"
```

## Offline build

On a machine with internet access and the same Python version (3.13):

```powershell
py -3.13 -m pip wheel -r packaging\requirements-build.txt wheel -w D:\mw-wheels
```

Use `pip wheel`, not `pip download`. One dependency (`hopcroftkarp`) is
published only as source, and `pip wheel` builds it here. The extra `wheel`
package is needed because `build.ps1` builds MetabWatch from the repo, and
`pyproject.toml` lists it as a build requirement.

Copy `D:\mw-wheels` to the build PC, then run:

```powershell
.\packaging\build.ps1 -Clean -Wheelhouse D:\mw-wheels
```

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| Self-test fails with `ModuleNotFoundError: X` | `X` is in `EXCLUDES`: remove it. If not, add `"X"` to `hiddenimports` in the spec. |
| Self-test fails with `Cannot find or load the C++ part of the library` (or another "DLL not found") | A package is loading a native DLL by file path, which PyInstaller cannot detect. Add it under `binaries` in the spec at the same relative location; see the IsoSpecPy entry. |
| Self-test fails at "Thermo .raw reader" | Check that `ext_lib` is collected in the spec, and that .NET Framework 4.x is present (it ships with Windows 10/11). |
| Exe does nothing when double-clicked | Look at the newest log in `%LOCALAPPDATA%\MetabWatch\logs\`. |
| Antivirus quarantines the exe | The exe is not code-signed. Ask IT to allow the file (by SHA-256) or to sign it. UPX is deliberately off. |
| `py -3.13` not found | Install Python 3.13 x64, or pass `-Python "C:\Path\to\python.exe"`. |
| Build is slow or uses an old package | Run with `-Clean`. |
