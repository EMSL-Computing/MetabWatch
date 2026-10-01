# Windows install

Set up MetabWatch on a lab Windows PC and make a desktop shortcut.

**IT / anyone installing:** follow this page once per machine.

**Operators:** after install, double-click the shortcut and use the window
([README](../README.md)). No terminal needed.

There are two ways to install:

- **[Standalone exe](#standalone-exe-recommended)** (recommended for lab PCs):
  a single file. No Python, no internet access.
- **[From source](#from-source-developers)**: Python venv plus git clone. Use
  this for development or if the exe is not an option.

## Standalone exe (recommended)

Get `MetabWatch-X.Y.Z.exe` (and its `.sha256`) from the GitLab Release or the
lab share. Maintainers build it with [BUILDING.md](BUILDING.md).

1. Copy the exe to a folder on the PC's **local** disk, for example
   `C:\MetabWatch\`. Do **not** run it straight from a network share: .NET
   will not load the Thermo reader from a remote path, and startup is slower.
2. Optional: check the file arrived intact by comparing its hash with the
   `.sha256` file:
   ```powershell
   Get-FileHash C:\MetabWatch\MetabWatch-X.Y.Z.exe -Algorithm SHA256
   ```
3. Optional health check (no window opens; prints PASS/FAIL to a text file):
   ```powershell
   C:\MetabWatch\MetabWatch-X.Y.Z.exe --self-test C:\MetabWatch\self-test.txt
   ```
4. Right-click the exe → **Send to** → **Desktop
   (create shortcut)** (Windows 11: **Show more options** first). Rename the
   shortcut **`MetabWatch X.Y.Z`**.

Double-click the shortcut. The window takes about 10–15 seconds to appear
while the exe unpacks itself. That is normal.

**Upgrading:** copy the new `MetabWatch-X.Y.Z.exe` next to the old one and make
a new shortcut. Delete the old exe and shortcut once the new one works.
Settings and results are stored in the folders you choose, not inside the exe.

**Logs:** the exe has no console window. Output and errors go to
`%LOCALAPPDATA%\MetabWatch\logs\` (the newest 20 logs are kept). Send the
newest log with any bug report.

## From source (developers)

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

### Desktop shortcut (one per release)

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
| Exe: nothing happens / error dialog | Newest log in `%LOCALAPPDATA%\MetabWatch\logs\`; run `--self-test` |
| Exe: antivirus removes or blocks it | Ask IT to allow the file (by SHA-256); it is not code-signed |
| Exe: Thermo `.raw` fails to open | Make sure the exe is on a local disk, not a network share |
| Shortcut flashes and closes | Run the Target line in PowerShell |
| “Virtual-environment Python was not found” | Create `.venv` in the repo root (see From source) |
| “MetabWatch is not installed” | `pip install .` into that `.venv` |
| GUI opens but Thermo `.raw` fails | Reinstall (`pip install .`). Thermo setup is documented by [CoreMS](https://github.com/EMSL-Computing/CoreMS) |
| Wrong code after an update | `git pull`, then `pip install .`; keep shortcut **Start in** and `-File` on this clone |
