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

### Offline lab PCs (by design)

Instrument / generator machines are often **not on the internet**. MetabWatch is set up for that:

- The package **vendors Plotly.js** under `src/synthesis/static/` (shipped via `package-data` in `pyproject.toml`).
- When a real dashboard is built, that file is **copied into the results folder** next to `dashboard.html` (about 4 MB). Charts load from this local copy — **no CDN and no network** at view time.
- At **run start**, if `dashboard.html` is missing, MetabWatch writes a **waiting page** (“Processing first sample…”) so **Open dashboard** works before the first sample finishes. After the first successful synthesis, that file is replaced with the full compound index.

After any `git pull` or upgrade on a lab machine, reinstall into the venv so the static asset is present:

```powershell
.\.venv\Scripts\Activate.ps1
pip install -e .
```

Confirm the vendored file exists (path relative to the clone):

```text
src\synthesis\static\plotly-2.35.2.min.js
```

If that file is missing, plots will not render offline even though the compound table may still appear.

## Smoke-test the launcher

From the **repo root**:

```powershell
.\Start-MetabWatch.ps1
```

The MetabWatch GUI should open with an empty form (preset mode). Close it when you have confirmed that.

If it fails, run the same command in a PowerShell window and read the error (common causes: missing `.venv`, or package not installed with `pip install -e .`).

**Dashboard smoke (optional, after a short process run):**

1. Start a run with a small input set; use **Open dashboard** while the first sample is still running — you should see the waiting page (auto-refresh every 15 s).
2. After processing finishes, refresh — full table and overview plots should appear.
3. Confirm the results folder contains `plotly-2.35.2.min.js` next to `dashboard.html`.
4. On an offline PC (or with the browser offline), open `dashboard.html` again and confirm plots still draw.

## Desktop shortcut (one per release)

Create **one desktop shortcut per MetabWatch release**. Always include the **version number** in the shortcut name so users know which install they are launching.

**Name the shortcut after the package version**, for example:

```text
MetabWatch 0.2.0
```

Use the version from `pyproject.toml` (also shown in the GUI window title). When you ship a new release, create a **new** shortcut for that version (and retire or replace the old one as appropriate).

### Steps

1. Right-click the **Desktop** → **New** → **Shortcut**.
2. For **location of the item**, paste the following (edit the path to **this** clone):

```text
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\path\to\your\MetabWatch\Start-MetabWatch.ps1"
```

3. Click **Next**.
4. Name it using the version, e.g. **`MetabWatch 0.2.0`**.
5. Click **Finish**.
6. Right-click the new shortcut → **Properties**.
7. Set **Start in** to the repo root, e.g. `C:\path\to\your\MetabWatch`.
8. Click **OK**.

Double-click **MetabWatch 0.2.0** (or the current version name). The GUI should open. Generators pick method, folders, and press **Start** in the window.

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
| Dashboard table OK but **plots blank** (offline PC) | Missing local Plotly: reinstall package (`pip install -e .`); confirm `src\synthesis\static\plotly-*.min.js` exists; re-run synthesis / process once so results get a fresh copy of `plotly-*.min.js` next to `dashboard.html`. HTML must **not** load `cdn.plot.ly` (old builds did). |
| **Open dashboard** says not found | Start a run first (waiting page is written at pipeline start), or open after folders are set so the GUI can write the placeholder |
| Waiting page never becomes full dashboard | First sample not finished or synthesis failed — check the live log; look for `[synthesized] Dashboard:` |

## Releases

Versioned releases are cut from `dev` into `main` on internal GitLab (version bump + [CHANGELOG.md](CHANGELOG.md) in one merge request). Full checklist: [RELEASING.md](RELEASING.md).

After a release, create a **new** desktop shortcut named with that version (see above) so generators launch the intended install.

## Related

- User-facing package overview: [README.md](../README.md)
- Release process and changelog: [RELEASING.md](RELEASING.md), [CHANGELOG.md](CHANGELOG.md)
- Pipeline config reference: [pipeline-reference.md](pipeline-reference.md)
