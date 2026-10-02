# Windows install

Set up MetabWatch on a lab Windows PC and make a desktop shortcut.

**IT / anyone installing:** follow this page once per machine.

**Operators:** after install, double-click the shortcut and use the window
([README](../README.md)). No terminal needed.

There are two ways to install:

- **[Standalone exe](#standalone-exe-recommended)** (recommended for lab PCs):
  a single file. No Python, no internet access.
- **[From source](#from-source-developers)**: Python venv plus git clone. Use
  this for development or if the exe is not an option. PCs without internet
  can install from a prepared bundle; see [Offline PCs](#offline-pcs-no-internet).

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

### Offline PCs (no internet)

Use this when a lab PC needs a source install but cannot reach PyPI. You
prepare a bundle on an online PC, copy it over (USB, LAN share, ...), and
install from it. If you do not need the source install, the
[standalone exe](#standalone-exe-recommended) is simpler.

**Use the same Python version on both PCs.** Packages such as numpy and scipy
ship as wheels built for one Python minor version (`cp313` = Python 3.13). A
wheelhouse built with Python 3.13 only installs on Python 3.13. The steps below
use 3.13, the version the exe is built and tested with.

#### A. Prepare the bundle (online Windows PC)

Requires 64-bit Python 3.13 and a clone of this repo.

1. Check out the release you want to deploy:
   ```powershell
   git checkout vX.Y.Z
   ```
2. Build the wheelhouse:
   ```powershell
   py -3.13 -m pip wheel . -c packaging\requirements-build.txt -w offline\wheelhouse
   ```
   - `pip wheel` (not `pip download`): one dependency, `hopcroftkarp`, is
     published only as source. `pip wheel` builds it, and MetabWatch itself,
     into wheels here, so the offline PC never has to build anything.
   - `-c packaging\requirements-build.txt` pins every package to the versions
     the exe is built and tested with.
   - Check that `offline\wheelhouse` contains only `.whl` files, about 70 files
     and 160 MB.
3. Export the source for the same release:
   ```powershell
   git archive --format=zip --prefix=MetabWatch-X.Y.Z/ -o offline\MetabWatch-X.Y.Z-source.zip vX.Y.Z
   ```
4. Download the **Windows installer (64-bit)** for the same Python 3.13.x from
   [python.org](https://www.python.org/downloads/windows/) into `offline\`.
   This `.exe` installs fully offline; do not use the web installer.
5. Zip `offline\` as `MetabWatch-X.Y.Z-offline.zip` and copy it to the lab PC.

#### B. Install (offline PC)

1. Unzip `MetabWatch-X.Y.Z-offline.zip` to a local folder, for example
   `C:\MetabWatch-offline\`.
2. Run the Python installer. Keep **tcl/tk and IDLE** ticked (it is by default),
   because the GUI needs tkinter.
3. Unzip `MetabWatch-X.Y.Z-source.zip` to a local disk. It creates a
   `MetabWatch-X.Y.Z\` folder, for example `C:\MetabWatch-X.Y.Z\`.
4. In PowerShell, from that folder:
   ```powershell
   py -3.13 -m venv .venv
   .\.venv\Scripts\python.exe -m pip install --no-index --find-links C:\MetabWatch-offline\wheelhouse metabwatch
   ```
   Install `metabwatch` by **name**, not with `pip install .`. Installing from
   the folder would build from source, and that needs internet access.
5. Smoke-test with `.\Start-MetabWatch.ps1`, then make the
   [desktop shortcut](#desktop-shortcut-one-per-release) pointing at this
   folder.

**Upgrading:** build a new bundle for the new release and install it into a
new `MetabWatch-X.Y.Z\` folder with a new shortcut. There is no `git pull` on
an offline PC. Delete the old folder and shortcut once the new one works.

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

Log lines are timestamped by default. To turn this off, add
`--no-log-timestamps` after the `.ps1` path in the shortcut's **Target**. See
[GUI options](cli.md#gui-options).

## Troubleshooting

| Symptom | What to check |
|---------|----------------|
| Exe: nothing happens / error dialog | Newest log in `%LOCALAPPDATA%\MetabWatch\logs\`; run `--self-test` |
| Exe: antivirus removes or blocks it | Ask IT to allow the file (by SHA-256); it is not code-signed |
| Exe: Thermo `.raw` fails to open | Make sure the exe is on a local disk, not a network share |
| Offline: `No matching distribution found` | The wheelhouse was built with a different Python version, or with `pip download` instead of `pip wheel`. Rebuild it (see [Offline PCs](#offline-pcs-no-internet)) |
| Offline: pip tries to reach the internet | You ran `pip install .`. Use `pip install --no-index --find-links <wheelhouse> metabwatch` |
| Shortcut flashes and closes | Run the Target line in PowerShell |
| “Virtual-environment Python was not found” | Create `.venv` in the repo root (see From source) |
| “MetabWatch is not installed” | `pip install .` into that `.venv` |
| GUI opens but Thermo `.raw` fails | Reinstall (`pip install .`). Thermo setup is documented by [CoreMS](https://github.com/EMSL-Computing/CoreMS) |
| Wrong code after an update | `git pull`, then `pip install .`; keep shortcut **Start in** and `-File` on this clone |
