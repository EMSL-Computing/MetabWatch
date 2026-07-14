# LCMS QC (Watcher Workflow)

This project is designed to run in a "watcher" style for routine QC: point it at a raw-data folder, leave it running, and it will process each new stable `.raw` file and refresh an HTML dashboard.

## Quick Start (Non-Coder)

1. Choose a config file:
   - `data/hilic_pipeline_config.json` for HILIC
2. Start the watcher:

```bash
python src/pipeline.py --mode watch --config data/hilic_pipeline_config.json
```

3. Drop new `.raw` files into the configured raw directory.
4. Open the generated dashboard at the output path in your config (for the HILIC example: `data/results_hilic_pos/dashboard.html`).

The watcher avoids duplicate processing by tracking file status in `pipeline_manifest.json`.

## What You Get

- A per-sample matches CSV (`*_targeted_matches.csv`)
- A per-sample MS1 trace CSV (`*_ms1_traces.csv`)
- A refreshed compound dashboard (`dashboard.html`)
- Per-compound pages in `compounds/`
- Wide pivot CSV exports (feature rows × sample columns): `export_mz.csv`, `export_rt.csv`, `export_height.csv`

## Common Commands

One-pass watch cycle (useful for scheduled runs):

```bash
python src/pipeline.py --mode watch --config data/hilic_pipeline_config.json --once
```

Force reprocessing of already completed files:

```bash
python src/pipeline.py --mode watch --config data/hilic_pipeline_config.json --once --force-reprocess
```

Process one explicit raw file:

```bash
python src/pipeline.py --mode process --config data/hilic_pipeline_config.json --raw data/raw_positive/your_file.raw
```

### Local smoke tests (Makefile)

End-to-end regression checks against configs under `data/`: always `--once --force-reprocess`, then verify dashboard / exports exist.

Put Thermo `.raw` files in `data/raw_positive/` (gitignored), or use `make get-test-data` once a download URL is configured.

```bash
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

By default the pipeline runs in `targeted` mode against `processor.standards_csv`. To run untargeted instead, add a `search_space` block to the JSON config:

```json
"search_space": {
  "mode": "untargeted",
  "top_n": 100
}
```

In untargeted mode the first sample matching `watcher.sample_name_regex` is used to seed the search space:

1. CoreMS untargeted peak picking + integration runs on that sample.
2. The top `top_n` peaks (ranked by integrated area, descending) are written to `<output_dir>/untargeted_search_space.csv` with synthetic compound names `feature_001`, `feature_002`, …, `unknown` ion types, and the sample's polarity.
3. The same sample is then processed against that search space (so it appears in the dashboard alongside every other sample).
4. All subsequent samples reuse the persisted CSV.

To rebuild the search space, delete `<output_dir>/untargeted_search_space.csv` and rerun. `processor.standards_csv` is optional in untargeted mode.

A ready-made example config lives at [data/hilic_pipeline_config_untargeted.json](data/hilic_pipeline_config_untargeted.json).

Dashboard caveat: the landing-page mass-accuracy and retention-time overview plots no longer have a truth anchor in untargeted mode. Each feature is plotted relative to its **per-feature batch mean** observed mz/rt; the y-axis shows ppm/min deviation from that mean. The "Avg ppm" / "Avg RT Error" columns in the compound table still show error against the search-space-CSV value (which itself came from the bootstrap sample), not deviation from a known truth — the column tooltips spell this out.

## Technical Documentation

- Pipeline configuration and runtime details: [docs/pipeline-reference.md](docs/pipeline-reference.md)
- Single-file processor details: [docs/single-file-search.md](docs/single-file-search.md)

## Requirements

Install the package (and its dependencies) from the repository root:

```bash
pip install -e .
```

### CoreMS

This workflow requires **[CoreMS 4.0.1](https://pypi.org/project/CoreMS/4.0.1/)** (declared in `pyproject.toml`). It is installed automatically with `pip install -e .`.

CoreMS provides LC-MS peak picking, integration, and Thermo `.raw` file reading used by the single-file processor and untargeted bootstrap path.

**Thermo `.raw` access:** CoreMS needs `pythonnet` for Thermo raw files.

- Windows: `pip install pythonnet`
- macOS / Linux: install Mono (`brew install mono` on macOS), then `pip install pythonnet`

See the [CoreMS installation docs](https://github.com/EMSL-Computing/CoreMS#installation) for details.
