# Changelog

All notable changes to MetabWatch are documented here.

Format inspired by [Keep a Changelog](https://keepachangelog.com/).
Versions follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.1.0] - 2026-07-22

First tagged release of the work accumulated on `dev` since `main`.

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

### Fixed

- Restored the GUI path without Windows exe packaging complexity.
