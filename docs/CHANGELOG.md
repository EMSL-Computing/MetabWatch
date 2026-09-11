# Changelog

All notable changes to MetabWatch are documented here.

Format inspired by [Keep a Changelog](https://keepachangelog.com/).
Versions follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- Repository `LICENSE`: Battelle Memorial Institute 2026 BSD-style terms and DOE / PNNL disclaimer.

## [0.3.0] - 2026-09-09

### Added

- GUI **Create custom config** helper: collect input/output folders, targeted vs untargeted, optional polarity (Auto / Positive / Negative) and Project ID, and RP thresholds, then write a new folder (`metabwatch_config`, or `_2` if that name is taken) with a simplified `metabwatch_config.json` (polarity and `project_id` written only when not Auto / empty), a copy of the RP CoreMS TOML, a `README.txt` (JSON keys and sample-name filter in plain language), and (targeted) a blank `monitored_compounds.csv`. Existing folders are not overwritten. Fill the compound list before a targeted Start. Packaged presets are not modified.
- Delayed hover notes on main-window and Create custom config labels so each field can be read without opening the docs.
- Optional project / batch filename filter (`project_id`, CLI `--project-id`, GUI Project ID). Empty means no extra filter; the preset regex still applies.
- Landing-page summary of compounds below 20% and 30% CV (count and percent) for Intensity and Area, under the reproducibility overview.
- Optional run polarity (GUI Auto / Positive / Negative, CLI `--polarity`, JSON `polarity`). When set, the output folder locks before the first sample; omit to auto-detect from the first successful file.
- Olympic LC / Eclipse 01 method presets (`hilic_metab_olympic_eclipse01`, `rp_metab_olympic_eclipse01`) with HILIC RT window 0.6 min and RP 0.2 min.

### Changed

- GUI **Method preset** is a dropdown of packaged presets (not radio buttons).
- Untargeted preset sample filter is `Pool` (case-insensitive) instead of `Pooled`, so lab pool filenames match.
- Packaged HILIC/RP QC lists use Aug 2026 Olympic LC / Eclipse 01 retention times; compounds or ion types without numeric values in that list are omitted (Sulfanilamide dropped from HILIC). HILIC Umbelliferone 1.0 min, Chlorogenic acid 5.2 min, Astilbin 4.0 min. General `*_metab_pnnl` keys keep the wider RT windows (0.8 / 0.4 min).
- Compound pages put the EIC overlay above across-sample metrics, with Previous and Next compound links stacked opposite Back to compound index (both wrap).
- When polarity is set up front (GUI Positive/Negative, CLI `--polarity`, JSON `polarity`), a mixed input folder no longer hard-stops the rest of the batch after the first opposite-polarity file. Matching files still run. Auto polarity still hard-stops a mixed batch.
- Packaged CoreMS TOMLs list only LC-MS overrides vs CoreMS 4.0.1 defaults that MetabWatch uses (peak picking, EIC integration, clustering). Formula-search, MS2, and FT-ICR dump keys are omitted.
- Packaged HILIC and RP CoreMS presets set `ph_inten_min_rel` and `ph_persis_min_rel` to `0.003` (CoreMS default `0.001`). Persistence is raised with intensity because CoreMS requires `ph_persis_min_rel >= ph_inten_min_rel`. These floors apply to untargeted peak picking only.
- Packaged CoreMS TOMLs enable `remove_mass_features_by_peak_metrics`. Untargeted bootstrap applies keep-rules after post-cluster integration: `noise_score_max >= 0.8`, `noise_score_min >= 0.5`, `gaussian_similarity >= 0.7`, `tailing_factor <= 1.5`. Gaussian similarity is read from CoreMS 4.0.1's private `_gaussian_similarity` (the public name is missing and would drop every feature). Targeted never calls this path.
- Targeted and untargeted peak picking follow MetaMS: if all MS1 scans are centroided, switch to `centroided_persistent_homology` (and relative-abundance MS1 noise); if all are profile, use `persistent homology`. Mixed MS1 formats raise.
- Packaged HILIC targeted QC lists no longer monitor Hesperetin (pos/neg), Syringaldehide (pos/neg), or L-Glutamine (neg). L-Glutamine remains on HILIC pos. RP lists are unchanged.
- Per-sample files leave the results root: match CSVs go to `matches/`, TIC plots and MS1 traces to `traces/`. The root keeps the dashboard, wide exports, and `compounds/`. Existing root-level `*_targeted_matches.csv` / `*_tic.png` / `*_ms1_traces.csv` / `*_eics.pdf` are moved on the next process or dashboard rebuild.
- Docs: landing README is GUI-first. CLI flags and JSON live in `docs/cli.md`. Lab Windows setup is `docs/INSTALL.md`. `docs/MAINTAINER.md` is the short development page (CoreMS for Thermo/pythonnet; macOS is developers only). Removed `docs/pipeline-reference.md` and `docs/single-file-search.md`.

### Fixed

- GUI hover notes use explicit black text so they stay visible on macOS dark mode.
- Create custom config popup grows when switching to Untargeted so Top N does not cover Save/Cancel.
- Compound EIC overlay: apex markers follow the match CSV (`observed_rt` / detected), including when only the `target_*` chromatogram was exported; dotted lines are reserved for true non-detects.
- Targeted MS1 export writes `mf_*` EIC columns with the same nearest-EIC fallback as target traces when the mass-feature EIC is missing.
- Compound-page header now reports how many samples have a picked peak (`detected_count`), not how many EIC traces are overlaid. Dotted non-detect traces no longer inflate the count.

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
