# MetabWatch

**MetabWatch** (package: `metabwatch`) is an automated LC–MS metabolomics quality-control workflow. Point it at a raw-data folder, leave it running, and it will process each new stable Thermo `.raw` file and refresh an HTML compound dashboard.

## Quick Start (Non-Coder)

1. Install (editable) from the repository root:

```bash
pip install -e .
```

2. Start a standard run with **method**, **search mode**, **input folder**, and **output folder** only:

```bash
metabwatch --method hilic_metab_pnnl --search targeted \
  --input /path/to/raw_folder \
  --output /path/to/results
```

| `--method` | Display name | `--search` | What it uses |
|------------|--------------|------------|--------------|
| `hilic_metab_pnnl` | PNNL Standard HILIC Metabolomics Method | `targeted` | HILIC CoreMS params + HILIC QC compounds (general RT window) |
| `hilic_metab_pnnl` | PNNL Standard HILIC Metabolomics Method | `untargeted` | HILIC CoreMS params (bootstrap search space) |
| `hilic_metab_olympic_eclipse01` | PNNL Standard HILIC Metabolomics Method — Olympic LC / Eclipse 01 | `targeted` | Same HILIC QC list, tighter RT window |
| `rp_metab_pnnl` | PNNL Standard RP Metabolomics Method | `targeted` | RP CoreMS params + RP QC compounds (general RT window) |
| `rp_metab_pnnl` | PNNL Standard RP Metabolomics Method | `untargeted` | RP CoreMS params (bootstrap search space) |
| `rp_metab_olympic_eclipse01` | PNNL Standard RP Metabolomics Method — Olympic LC / Eclipse 01 | `targeted` | Same RP QC list, tighter RT window |

Built-in defaults (no extra flags needed):

| Method | m/z ppm | RT (min) | min area | Sample name filter |
|--------|---------|----------|----------|--------------------|
| PNNL Standard HILIC Metabolomics Method | 5 | 0.8 | 1000 | Targeted: `QC_Metab_(.+)` · Untargeted: `Pool` (case-insensitive) |
| PNNL Standard HILIC — Olympic LC / Eclipse 01 | 5 | 0.3 | 1000 | same filters as above |
| PNNL Standard RP Metabolomics Method | 5 | 0.4 | 20000 | same filters as above |
| PNNL Standard RP — Olympic LC / Eclipse 01 | 5 | 0.2 | 20000 | same filters as above |

Or as a module:

```bash
python -m metabwatch.pipeline --method hilic_metab_pnnl --search targeted \
  -i /path/to/raw_folder -o /path/to/results
```

3. Drop new `.raw` files into the input folder.
4. Open the generated dashboard at `<output>/dashboard.html`.

### GUI (Windows)

**Recommended for non-coders:** double-click **`Start-MetabWatch.ps1`** in the repo root, or use a desktop shortcut created by a maintainer (named with the version, e.g. `MetabWatch 0.2.0`). Setup and shortcut steps: [docs/MAINTAINER.md](docs/MAINTAINER.md).

For developers, after `pip install -e .`:

```bash
metabwatch-gui
# or:
python -m metabwatch.gui
```

The window provides:

- **Preset shortcuts** — Method preset dropdown (packaged HILIC / RP methods) × targeted or untargeted, optional polarity and project ID, plus input/output folder pickers
- **Custom JSON** — browse to a pipeline config file (same schema as `metabwatch --config`)
- **Watch continuously** or **Process once**, optional force reprocess
- **Start / Stop** (stop finishes the current file, then exits the watch loop)
- Live log, **Open dashboard**, and **Open output**

Requires a Python install that includes **tkinter** (the official [python.org](https://www.python.org/downloads/) Windows installer does). Thermo `.raw` support needs `pythonnet` (and Mono on macOS/Linux).

**macOS note:** TIC plots use a non-interactive matplotlib backend so the GUI does not freeze after the first sample. Prefer **Process once** for a single batch; **Watch continuously** keeps running (idle between files) until you press Stop.

The watcher detects new files via filesystem notifications (`watchdog`) with a periodic directory-scan fallback (`discovery_mode`: `hybrid` by default). Files are processed only after they remain unchanged for `stability_wait_sec` (Thermo creation events fire before writing finishes). Duplicate processing is avoided via `pipeline_manifest.json`.

### One polarity per run

Each output folder is locked to a **single ionization polarity** (`positive` or `negative`). Optionally set it up front (GUI **Polarity** radios, CLI `--polarity`, or JSON `"polarity"`); otherwise the first successfully processed sample writes it into `pipeline_manifest.json`. Later samples must match. Opposite-polarity files are rejected; in multi-file batches the rest of the batch is hard-stopped. Use separate input/output folders for positive and negative acquisitions.

The dashboard header shows the run polarity (and warns if legacy mixed outputs are present).

## What You Get

- A per-sample matches CSV (`*_targeted_matches.csv`)
- A per-sample MS1 trace CSV (`*_ms1_traces.csv`)
- A compound dashboard (`dashboard.html`) with polarity labeled (plots work offline; Plotly.js is copied into the results folder). A waiting page is written at run start so you can open the dashboard while the first sample is still processing
- Per-compound pages in `compounds/`
- Wide pivot CSV exports (feature rows × sample columns): `export_mz.csv`, `export_rt.csv`, `export_height.csv`, `export_area.csv`

## Common Commands

One-pass watch cycle (useful for scheduled runs):

```bash
metabwatch --method hilic_metab_pnnl --search targeted -i RAW -o OUT --once
```

Force reprocessing of already completed files:

```bash
metabwatch --method hilic_metab_pnnl --search targeted -i RAW -o OUT --once --force-reprocess
```

Process one explicit raw file:

```bash
metabwatch --method hilic_metab_pnnl --search targeted -i RAW -o OUT \
  --mode process --raw /path/to/file.raw
```

### Advanced: JSON config

For custom tolerances, sample filters, or CoreMS files, pass a JSON config instead of the preset flags (do not mix both):

```bash
metabwatch --config data/hilic_pipeline_config.json
```

Simplified flat JSON and legacy nested (`processor` / `watcher` / …) schemas are both supported. See [docs/pipeline-reference.md](docs/pipeline-reference.md).

### Local smoke tests (Makefile) for developers

End-to-end regression checks: always `--once --force-reprocess`, then verify dashboard / exports exist.

Put Thermo `.raw` files in `data/raw_positive/` (gitignored), or use `make get-test-data` once a download URL is configured.

```bash
make test-unit                  # unit tests (pytest)
make test-workflow-targeted     # PNNL HILIC targeted via preset CLI
make test-workflow-untargeted   # advanced JSON (QC_Metab fixtures)
make test-workflow              # both
make get-test-data              # download test .raw files when URL is set; else check local
make help                       # list targets and override variables
```

```bash
make test-workflow-targeted PYTHON=./venv/bin/python
```

## Search-space modes

**Targeted** (`--search targeted`) matches against the packaged QC compound list for the method.

**Untargeted** (`--search untargeted`) seeds the search space from the first sample whose name matches the untargeted filter (`Pool` by default):

1. CoreMS untargeted peak picking + integration runs on that sample.
2. The top `top_n` peaks (ranked by integrated area, descending) are written to `<output_folder>/untargeted_search_space.csv` with synthetic compound names `feature_001`, `feature_002`, …, `unknown` ion types, and the sample's polarity.
3. The same sample is then processed against that search space (so it appears in the dashboard alongside every other sample).
4. All subsequent samples reuse the persisted CSV.

Packaged CoreMS TOML and QC CSVs live under `src/presets/<method_key>/` (installed with the package). QC retention times come from the Aug 2026 Olympic LC / Eclipse 01 list; general method keys use a wider RT window so the same list can be used on other LC/MS systems.

## Technical Documentation

- Pipeline configuration and runtime details: [docs/pipeline-reference.md](docs/pipeline-reference.md)
- Single-file processor details: [docs/single-file-search.md](docs/single-file-search.md)
- Windows lab setup and desktop shortcut: [docs/MAINTAINER.md](docs/MAINTAINER.md)
- Changelog: [docs/CHANGELOG.md](docs/CHANGELOG.md)
- Cutting a release (maintainers): [docs/RELEASING.md](docs/RELEASING.md)

## Requirements

Install the package (and its dependencies) from the repository root:

```bash
pip install -e .
```

This installs the `metabwatch` console command.

### CoreMS

This workflow requires **[CoreMS](https://pypi.org/project/CoreMS)** (declared in `pyproject.toml`). It is installed automatically with `pip install -e .`.

CoreMS provides LC-MS peak picking, integration, and Thermo `.raw` file reading used by the single-file processor and untargeted bootstrap path.

**Thermo `.raw` access:** CoreMS needs `pythonnet` for Thermo raw files.

- Windows: `pip install pythonnet`
- macOS / Linux: install Mono (`brew install mono` on macOS), then `pip install pythonnet`
