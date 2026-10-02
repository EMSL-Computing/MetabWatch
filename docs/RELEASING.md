# Releasing MetabWatch

How maintainers cut a versioned release. Day-to-day work stays on **internal GitLab** (`origin` → `code.emsl.pnl.gov`). The published release is the **GitHub Release** on `EMSL-Computing/MetabWatch`. Create the version tag on GitLab and push it; the mirror already copies tags to GitHub. There is no GitLab Release for a version. Keep the process simple: human-edited changelog, version bump only at release time, one merge request into `main`.

## Day-to-day

1. Land feature work on **`dev`** (merge requests into `dev`).
2. Do **not** bump `pyproject.toml` version on feature MRs.
3. Optionally jot bullets under `## [Unreleased]` in [CHANGELOG.md](CHANGELOG.md) when a change is user-visible (nice-to-have, not required).

## Cut a release

1. Start from up-to-date `dev`:
   ```bash
   git checkout dev
   git pull origin dev
   ```
2. Decide the next version (semantic versioning: patch / minor / major).
3. **Draft notes from `main`:**
   ```bash
   git fetch origin
   git log origin/main..HEAD --oneline --no-merges
   ```
   Or use GitLab: **Repository → Compare**, source `dev` vs target `main`.

   Edit the list into categorized bullets under a new section in `docs/CHANGELOG.md`:
   ```markdown
   ## [X.Y.Z] - YYYY-MM-DD

   ### Added
   - ...

   ### Changed
   - ...

   ### Fixed
   - ...
   ```
   Leave `## [Unreleased]` empty (or only keep work still not shipping).
4. **Bump version** in both places (keep them in sync):
   - `pyproject.toml` → `[project].version`
   - `src/__init__.py` → `_FALLBACK_VERSION`
5. Commit on `dev` (or a short-lived `release/X.Y.Z` branch from `dev`), for example:
   ```text
   Release X.Y.Z
   ```
6. Open an **MR `dev` → `main`** (or `release/X.Y.Z` → `main`) on internal GitLab. Paste the new changelog section into the MR description.
7. After the MR is merged to `main`:
   ```bash
   git checkout main
   git pull origin main
   git tag -a vX.Y.Z -m "MetabWatch X.Y.Z"
   git push origin main --tags
   ```
   That push creates the tag on GitLab. The mirror copies `main` and the tag to GitHub. The **Build Windows exe** workflow then runs `packaging/build.ps1 -Clean`, including the exe `--self-test`, and opens a **draft** GitHub Release titled `MetabWatch X.Y.Z` with `MetabWatch-X.Y.Z.exe` and `MetabWatch-X.Y.Z.exe.sha256`. Notes are the `## [X.Y.Z]` section of [CHANGELOG.md](CHANGELOG.md). Publish that draft after the checks in step 9. A push to `dev` does not start this build. [BUILDING.md](BUILDING.md) covers building the exe by hand on Windows.
8. Merge `main` back into `dev` if needed so `dev` has the release merge commit.
9. On that draft GitHub Release, before you publish it:
   - Download the exe and the `.sha256` file.
   - Check the checksum. The file is a lowercase hash, two spaces, then the file name. `Get-FileHash` prints uppercase:
     ```powershell
     (Get-FileHash .\MetabWatch-X.Y.Z.exe -Algorithm SHA256).Hash.ToLower()
     (Get-Content .\MetabWatch-X.Y.Z.exe.sha256).Split()[0]
     ```
   - Smoke-test the exe on real `.raw` files (one targeted run and one untargeted run).
   - Publish the draft. Copy both files to the lab share if that is how the lab PCs get them.
10. Lab machines:
    - **Exe installs:** copy the new exe to the PC and make a new versioned shortcut per [INSTALL.md](INSTALL.md#standalone-exe-recommended).
    - **Source installs:** `git pull`, then **always** reinstall into the lab venv (`pip install .` or `pip install -e .`) so package data is present, then create a new versioned desktop shortcut (e.g. `MetabWatch X.Y.Z`). A `git pull` alone is not enough if the install is stale.

### Offline dashboard assets (when relevant)

Dashboard charts ship **offline by default** (no CDN). Maintainers should treat the vendored Plotly bundle as part of the release surface:

| Item | Location |
|------|----------|
| Minified Plotly.js | `src/synthesis/static/plotly-*.min.js` (~4 MB; committed in git) |
| Filename pin in code | `PLOTLY_JS_FILENAME` in `src/synthesis/synthesizer.py` |
| Packaging | `pyproject.toml` → `[tool.setuptools.package-data]` → `"metabwatch.synthesis" = [..., "static/*"]` |

**If you upgrade Plotly.js:**

1. Download the matching `plotly-X.Y.Z.min.js` into `src/synthesis/static/`.
2. Update `PLOTLY_JS_FILENAME` (and any tests that assert the name).
3. Remove or stop shipping the old file so the tree stays clear.
4. Note the upgrade under **Changed** or **Fixed** in the changelog (lab impact: reinstall + next dashboard rebuild recopies the JS into each results folder).

**When cutting a release that touches packaging or the dashboard:**

- Confirm `static/*` is still listed in `package-data` (do not drop it when editing `pyproject.toml`).
- After install on a clean venv, confirm the file is reachable from the package tree (or that a one-sample smoke run writes `plotly-*.min.js` next to `dashboard.html`).

Existing results folders from older builds that still point at `cdn.plot.ly` will not plot offline until the dashboard is regenerated (reprocess once or let a new sample finish synthesis).

### Helper (optional)

From the repo root:

```bash
make changelog-draft
```

Prints `origin/main..HEAD` commit subjects for editing into `docs/CHANGELOG.md`. Does not edit files.

## First tagged release under this process

Use the normal cut-a-release steps. Choose the version with semver (for example **0.2.0** when shipping a feature set that was still labeled 0.1.0 on `dev`). Keep `pyproject.toml` and `_FALLBACK_VERSION` in sync, and put the notes under a new section in [CHANGELOG.md](CHANGELOG.md) drafted from `origin/main..HEAD`.

## Checklist

Do these in order. The commands are in [Cut a release](#cut-a-release) above.

- [ ] On `dev`, write `## [X.Y.Z]` in `docs/CHANGELOG.md` from `main..dev`. Move shipping notes out of `## [Unreleased]`.
- [ ] Set `X.Y.Z` in both `pyproject.toml` and `src/__init__.py` `_FALLBACK_VERSION`.
- [ ] Dependencies changed: refresh `packaging/requirements-build.txt` ([BUILDING.md](BUILDING.md#dependencies-changed)). Skip if they did not.
- [ ] Dashboard or packaging changed: the vendored Plotly file, the filename pin, and `static/*` in `package-data` still match. Skip if they did not.
- [ ] Merge the release MR from `dev` into `main`.
- [ ] On `main`, create annotated tag `vX.Y.Z` and push it to GitLab (`git push origin main --tags`).
- [ ] Merge `main` back into `dev`.
- [ ] On GitHub, wait until **Build Windows exe** is green. The draft release contains `MetabWatch-X.Y.Z.exe` and `MetabWatch-X.Y.Z.exe.sha256`.
- [ ] Download both files and confirm the checksum matches.
- [ ] Smoke-test the exe on one targeted `.raw` run and one untargeted run.
- [ ] Publish the draft. Copy both files to the lab share if the lab uses one.
- [ ] Update each lab PC per [INSTALL.md](INSTALL.md): new exe and shortcut, or `git pull`, `pip install .`, and a new shortcut.
- [ ] A lab PC installs from source with no internet: build `MetabWatch-X.Y.Z-offline.zip` ([INSTALL.md](INSTALL.md#offline-pcs-no-internet)). Skip if none do.
