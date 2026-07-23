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
9. Lab machines: `git pull`, reinstall if needed (`pip install -e .`), and create a new versioned desktop shortcut per [MAINTAINER.md](MAINTAINER.md) (e.g. `MetabWatch X.Y.Z`).

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
- [ ] MR into `main` opened and merged
- [ ] Annotated tag `vX.Y.Z` pushed to `origin`
- [ ] `dev` updated from `main` if needed
- [ ] Lab shortcuts updated for the new version
