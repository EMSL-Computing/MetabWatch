# Maintainer guide

How to set up MetabWatch for data generators (non-coders) on Windows, and how to create a desktop shortcut.

## Audience

- **Maintainers / IT:** install once per machine or lab PC, create the desktop shortcut.
- **Data generators:** double-click the shortcut; use the GUI only (no terminal, no Python).

## Prerequisites (Windows)

1. Install **64-bit Python 3.10+** from [python.org](https://www.python.org/downloads/).
   - Prefer the official installer so **tkinter** is included.
   - Optionally check **Add python.exe to PATH**.
2. Clone this repository to a local disk path (prefer a normal folder over OneDrive-only paths when possible).
3. In the repo root, create a virtual environment and install the package:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
pip install -e .
pip install pythonnet
```

`pythonnet` is required for Thermo `.raw` files.

## Smoke-test the launcher

From the **repo root**:

```powershell
.\Start-MetabWatch.ps1
```

The MetabWatch GUI should open with an empty form (preset mode). Close it when you have confirmed that.

If it fails, run the same command in a PowerShell window and read the error (common causes: missing `.venv`, or package not installed with `pip install -e .`).

## Desktop shortcut (one per release)

Create **one desktop shortcut per MetabWatch release**. Always include the **version number** in the shortcut name so users know which install they are launching.

**Name the shortcut after the package version**, for example:

```text
MetabWatch 0.1.0
```

Use the version from `pyproject.toml` (also shown in the GUI window title). When you ship a new release, create a **new** shortcut for that version (and retire or replace the old one as appropriate).

### Steps

1. Right-click the **Desktop** → **New** → **Shortcut**.
2. For **location of the item**, paste the following (edit the path to **this** clone):

```text
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\path\to\your\MetabWatch\Start-MetabWatch.ps1"
```

3. Click **Next**.
4. Name it using the version, e.g. **`MetabWatch 0.1.0`**.
5. Click **Finish**.
6. Right-click the new shortcut → **Properties**.
7. Set **Start in** to the repo root, e.g. `C:\path\to\your\MetabWatch`.
8. Click **OK**.

Double-click **MetabWatch 0.1.0** (or the current version name). The GUI should open. Generators pick method, folders, and press **Start** in the window.

## What the launcher does

`Start-MetabWatch.ps1` (repo root):

- Locates `.venv\Scripts\python.exe` / `pythonw.exe` next to the script
- Checks that `metabwatch.gui` is importable
- Starts an **unconfigured** GUI (`python -m metabwatch.gui`)

Raw and output folders are chosen in the GUI (or via Custom JSON in the form). They are not set by the PowerShell script.

## Troubleshooting

| Symptom | What to check |
|---------|----------------|
| Shortcut flashes and closes | Run the Target line in PowerShell to see the error |
| “Virtual-environment Python was not found” | Create `.venv` in the repo root (see Prerequisites) |
| “MetabWatch is not installed” | `pip install -e .` into that `.venv` |
| GUI opens but Thermo `.raw` fails | `pip install pythonnet` in the same `.venv` |
| Wrong code after an update | `git pull`, reinstall if needed (`pip install -e .`), keep shortcut **Start in** and `-File` path on this clone |

## Related

- User-facing package overview: [README.md](../README.md)
- Pipeline config reference: [pipeline-reference.md](pipeline-reference.md)
