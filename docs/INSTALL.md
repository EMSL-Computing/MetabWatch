# Windows install

Set up MetabWatch on a lab Windows PC and make a desktop shortcut.

**IT / anyone installing:** follow this page once per machine.

**Operators:** after install, double-click the shortcut and use the window
([README](../README.md)). No terminal needed.

## Install

1. Install **64-bit Python 3.10+** from [python.org](https://www.python.org/downloads/).
   Prefer the official installer so **tkinter** is included. Optionally check
   **Add python.exe to PATH**.
2. Clone this repository to a local disk path.
3. In the repo root:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
pip install .
```

After `git pull` or an upgrade, activate the venv and `pip install .` again.

Smoke-test from the repo root: `.\Start-MetabWatch.ps1`. The window should open
empty (preset mode). If it flashes and closes, run that command in PowerShell
and read the error (usually a missing `.venv` or `pip install .` not done).

## Desktop shortcut (one per release)

Name the shortcut after the package version from `pyproject.toml` (also in the
GUI title), for example `MetabWatch 0.3.0`. Create a **new** shortcut for each
release.

1. Right-click the **Desktop** → **New** → **Shortcut**.
2. Location (edit the path to **this** clone):

```text
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\path\to\your\MetabWatch\Start-MetabWatch.ps1"
```

3. Name it **`MetabWatch 0.3.0`** (or the current version). Finish.
4. Right-click the shortcut → **Properties**. Set **Start in** to the repo
   root, e.g. `C:\path\to\your\MetabWatch`. OK.

Double-click the shortcut. Pick method, folders, and **Start**.

`Start-MetabWatch.ps1` uses `.venv` next to the script and opens an unconfigured
GUI. Folders are chosen in the window, not by the script.

## Troubleshooting

| Symptom | What to check |
|---------|----------------|
| Shortcut flashes and closes | Run the Target line in PowerShell |
| “Virtual-environment Python was not found” | Create `.venv` in the repo root (see Install) |
| “MetabWatch is not installed” | `pip install .` into that `.venv` |
| GUI opens but Thermo `.raw` fails | Reinstall (`pip install .`). Thermo setup is documented by [CoreMS](https://github.com/EMSL-Computing/CoreMS) |
| Wrong code after an update | `git pull`, then `pip install .`; keep shortcut **Start in** and `-File` on this clone |
