# Changelog

All notable changes to MetabWatch are documented here.

Format inspired by [Keep a Changelog](https://keepachangelog.com/).
Versions follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- Optional run polarity (GUI Auto / Positive / Negative, CLI `--polarity`, JSON `polarity`). When set, the output folder locks before the first sample; omit to keep auto-detect from the first successful file.

### Changed

- Untargeted preset sample filter is now `Pool` (case-insensitive) instead of `Pooled`, so lab pool filenames match.

## [0.2.2] - 2026-08-04

### Added

- Offline dashboard charts: vendored Plotly.js is copied into the results folder (no CDN).
- Waiting-page `dashboard.html` at run start so the dashboard can be opened while the first sample is still processing.

### Changed

- Maintainer and release docs cover offline Plotly packaging, lab reinstall, and blank-plot troubleshooting.

### Fixed

- PNNL Standard RP Metabolomics Method CoreMS preset: use `persistent homology` peak picking and raised PH intensity/persistence floors so defaults are compatible with the pinned CoreMS release (closes #14).

## [0.2.1] - 2026-07-22

No functional changes; this is a patch release to update the changelog and docs for the 0.2.0 release.


## [0.2.0] - 2026-07-22

### Added

- Desktop GUI (`metabwatch-gui`) with preset shortcuts for PNNL Standard HILIC / RP methods × targeted or untargeted search, custom JSON mode, watch/once controls, and live log.
- Windows PowerShell launcher (`Start-MetabWatch.ps1`) and maintainer guidance for lab install and versioned desktop shortcuts.
- Single-polarity enforcement per output folder (manifest-backed); opposite-polarity samples are rejected.
- Filesystem watcher options via `watchdog`, with hybrid discovery and stability wait for Thermo `.raw` writes.
- Area CV and area histogram on the dashboard landing page.
- Unit tests and Makefile workflow smoke targets (targeted / untargeted).
- Simplified flat JSON pipeline config (legacy nested schema still supported).
- Maintainer changelog (`docs/CHANGELOG.md`), release process (`docs/RELEASING.md`), and `make changelog-draft`.

### Changed

- More specific display names for packaged RP and HILIC method presets.
- README and docs aligned with one polarity per run and current CLI/GUI entry points.
- Paths and project naming standardized on MetabWatch / `metabwatch`.
- Makefile and `.gitignore` updated for a repo-local `.venv`.

## [0.1.0]

Prior package version on `main` before the 0.2.0 release. No formal changelog was maintained for that line.
