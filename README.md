# MetabWatch

**MetabWatch** (package: `metabwatch`) is an automated LC–MS metabolomics quality-control workflow. Point it at a raw-data folder, leave it running, and it will process each new stable Thermo `.raw` file and refresh an HTML compound dashboard.

## Quick Start (Non-Coder)

1. Choose or write a simplified config JSON. The HILIC example is `data/hilic_pipeline_config.json`:

```json
{
  "input_folder": "data/raw_positive",
  "output_folder": "data/results_hilic_pos",
  "corems_params": "data/corems_params/monet_hilic_corems_lcms_params.toml",
  "targeted": true,
  "qc_compounds": "data/qc_search_space/hilic_qc_search.csv",
  "sample_name_regex": "QC_Metab_(.+)",
  "mz_tolerance_ppm": 4.0,
  "rt_tolerance": 0.8,
  "min_area": 1000
}
```

Required fields: `input_folder`, `output_folder`, `corems_params`, `targeted`, `sample_name_regex`, and (when `targeted` is `true`) `qc_compounds`. Optional: `mz_tolerance_ppm`, `rt_tolerance`, `min_area`, and other advanced knobs (see [docs/pipeline-reference.md](docs/pipeline-reference.md)).

2. Install (editable) and start the watcher:

```bash
pip install -e .
metabwatch --mode watch --config data/hilic_pipeline_config.json
```

Or as a module:

```bash
python -m metabwatch.pipeline --mode watch --config data/hilic_pipeline_config.json
```

3. Drop new `.raw` files into the configured raw directory (`input_folder`).
4. Open the generated dashboard at the output path in your config (for the HILIC example: `data/results_hilic_pos/dashboard.html`).

The watcher detects new files via filesystem notifications (`watchdog`) with a periodic directory-scan fallback (`discovery_mode`: `hybrid` by default). Files are processed only after they remain unchanged for `stability_wait_sec` (Thermo creation events fire before writing finishes). Duplicate processing is avoided via `pipeline_manifest.json`. Use `"discovery_mode": "poll"` to restore pure polling, or `"watchdog"` for events-only after startup reconciliation.

### One polarity per run

Each output folder is locked to a **single ionization polarity** (`positive` or `negative`). The first successfully processed sample writes that polarity into `pipeline_manifest.json`; later samples must match. Opposite-polarity files are rejected; in multi-file batches the rest of the batch is hard-stopped. Use separate input/output folders for positive and negative acquisitions.

The dashboard header shows the run polarity (and warns if legacy mixed outputs are present).

## What You Get

- A per-sample matches CSV (`*_targeted_matches.csv`)
- A per-sample MS1 trace CSV (`*_ms1_traces.csv`)
- A refreshed compound dashboard (`dashboard.html`) with polarity labeled
- Per-compound pages in `compounds/`
- Wide pivot CSV exports (feature rows × sample columns): `export_mz.csv`, `export_rt.csv`, `export_height.csv`

## Common Commands

One-pass watch cycle (useful for scheduled runs):

```bash
metabwatch --mode watch --config data/hilic_pipeline_config.json --once
```

Force reprocessing of already completed files:

```bash
metabwatch --mode watch --config data/hilic_pipeline_config.json --once --force-reprocess
```

Process one explicit raw file:

```bash
metabwatch --mode process --config data/hilic_pipeline_config.json --raw data/raw_positive/your_file.raw
```

### Local smoke tests (Makefile) for developers

End-to-end regression checks against configs under `data/`: always `--once --force-reprocess`, then verify dashboard / exports exist.

Put Thermo `.raw` files in `data/raw_positive/` (gitignored), or use `make get-test-data` once a download URL is configured.

```bash
make test-unit                  # config loader unit tests (pytest)
make test-workflow-targeted     # data/hilic_pipeline_config.json
make test-workflow-untargeted   # data/hilic_pipeline_config_untargeted.json
make test-workflow              # both
make get-test-data              # download test .raw files when URL is set; else check local
make help                       # list targets and override variables
```

```bash
make test-workflow-targeted PYTHON=./venv/bin/python
```

## Search-space modes

Set `"targeted": true` (with `qc_compounds` pointing at a standards CSV) for targeted matching. For untargeted, set `"targeted": false`:

```json
{
  "input_folder": "data/raw_positive",
  "output_folder": "data/results_hilic_pos_untargeted",
  "corems_params": "data/corems_params/monet_hilic_corems_lcms_params.toml",
  "targeted": false,
  "sample_name_regex": "QC_Metab_(.+)",
  "top_n": 100
}
```

In untargeted mode the first sample matching `sample_name_regex` is used to seed the search space:

1. CoreMS untargeted peak picking + integration runs on that sample.
2. The top `top_n` peaks (ranked by integrated area, descending) are written to `<output_folder>/untargeted_search_space.csv` with synthetic compound names `feature_001`, `feature_002`, …, `unknown` ion types, and the sample's polarity.
3. The same sample is then processed against that search space (so it appears in the dashboard alongside every other sample).
4. All subsequent samples reuse the persisted CSV.

A ready-made example config lives at [data/hilic_pipeline_config_untargeted.json](data/hilic_pipeline_config_untargeted.json).

Legacy nested configs (`processor` / `watcher` / `search_space`) are still accepted by the loader for more advanced use cases.


## Technical Documentation

- Pipeline configuration and runtime details: [docs/pipeline-reference.md](docs/pipeline-reference.md)
- Single-file processor details: [docs/single-file-search.md](docs/single-file-search.md)

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