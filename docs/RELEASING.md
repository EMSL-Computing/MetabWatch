# Releasing MetabWatch

How maintainers cut a versioned release. Hosted on **internal GitLab** (`origin` → `code.emsl.pnl.gov`). Keep this process simple: human-edited changelog, version bump only at release time, one merge request into `main`.

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
   Optionally create a GitLab **Release** from the tag in the UI (notes = the changelog section). Tags alone are enough if you do not use Releases.
8. Merge `main` back into `dev` if needed so `dev` has the release merge commit.
9. Lab machines: `git pull`, **always** reinstall into the lab venv (`pip install -e .`) so package data (presets **and** vendored Plotly under `src/synthesis/static/`) is present, then create a new versioned desktop shortcut per [MAINTAINER.md](MAINTAINER.md) (e.g. `MetabWatch X.Y.Z`). Offline dashboards depend on that static file being installed; a `git pull` alone is not enough if the editable install is stale.

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

- [ ] Changelog section for `X.Y.Z` written (from `main..dev`)
- [ ] `pyproject.toml` version = `X.Y.Z`
- [ ] `src/__init__.py` `_FALLBACK_VERSION` = `X.Y.Z`
- [ ] If dashboard/packaging changed: vendored `src/synthesis/static/plotly-*.min.js` present, filename pin matches, `package-data` still includes `static/*`
- [ ] MR into `main` opened and merged
- [ ] Annotated tag `vX.Y.Z` pushed to `origin`
- [ ] `dev` updated from `main` if needed
- [ ] Lab machines: `git pull` + `pip install -e .` (refreshes Plotly static asset) + versioned shortcut updated
