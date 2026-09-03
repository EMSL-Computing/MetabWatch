# Changelog

All notable changes to MetabWatch are documented here.

Format inspired by [Keep a Changelog](https://keepachangelog.com/).
Versions follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- GUI **Create custom config** helper: collect input/output folders, targeted vs untargeted, and RP thresholds, then write a new folder (`metabwatch_config`, or `_2` if that name is taken) with a simplified `metabwatch_config.json`, a copy of the RP CoreMS TOML, a `README.txt` (from `src/gui/starter_readme.txt`), and (targeted) a blank `monitored_compounds.csv` (header only, no packaged QC rows). Existing folders are not overwritten. The new JSON is selected as Custom JSON; fill the compound list before a targeted Start.
- Optional project / batch filename filter (`project_id`, CLI `--project-id`, GUI Project ID). Empty means no extra filter; the preset regex (`QC_Metab_` / `Pool`) still applies.
- Landing-page summary of compounds below 20% and 30% CV (count and percent) for Intensity and Area, under the reproducibility overview.
- Optional run polarity (GUI Auto / Positive / Negative, CLI `--polarity`, JSON `polarity`). When set, the output folder locks before the first sample; omit to keep auto-detect from the first successful file.
- Olympic LC / Eclipse 01 method presets (`hilic_metab_olympic_eclipse01`, `rp_metab_olympic_eclipse01`) with tighter RT windows (0.3 min HILIC, 0.2 min RP).

### Changed

- HILIC QC retention times: Umbelliferone 1.0 min and Chlorogenic acid 5.2 min (both `hilic_metab_pnnl` and `hilic_metab_olympic_eclipse01`). RP values are unchanged.
- GUI **Method preset** is a dropdown of packaged presets (not radio buttons) so more presets can be added without growing the window.
- Untargeted preset sample filter is now `Pool` (case-insensitive) instead of `Pooled`, so lab pool filenames match.
- Packaged HILIC/RP QC presets: omit a compound from a method when the Aug 2026 list has no numeric RT for that method, and omit an ion type when that list has no numeric [M+H]+ or [M-H]-. Sulfanilamide dropped from HILIC (no RT(HILIC)); polarity rows were already aligned.
- QC compound retention times in the packaged HILIC and RP search spaces now come from the Aug 2026 Olympic LC / Eclipse 01 list. General `*_metab_pnnl` keys keep the wider RT windows (0.8 / 0.4 min).

### Fixed

- Compound EIC overlay: apex markers follow the match CSV (`observed_rt` / detected), including when only the `target_*` chromatogram was exported; dotted lines are reserved for true non-detects. Markers use a light fill and dark outline so they stay visible on newest-darkest traces.
- Targeted MS1 export writes `mf_*` EIC columns with the same nearest-EIC fallback as target traces when the mass-feature EIC is missing.

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
