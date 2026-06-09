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

## Technical Documentation

- Pipeline configuration and runtime details: [docs/pipeline-reference.md](docs/pipeline-reference.md)
- Single-file processor details: [docs/single-file-search.md](docs/single-file-search.md)

## CoreMS Version Note

This workflow currently depends on a CoreMS development commit:
https://github.com/EMSL-Computing/CoreMS/commit/88f6d0021ed594b5d0a3efe6285f8379858fd039
