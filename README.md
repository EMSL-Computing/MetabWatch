# LCMS QC
This repository contains scripts for performing quality control (QC) on liquid chromatography-mass spectrometry (LCMS) data using the CoreMS software.  The scripts are designed to process raw LCMS data files, perform a targeted search for specific compounds.

# CoreMS
This uses a DEVELOPMENT version of CoreMS available at https://github.com/EMSL-Computing/CoreMS/commit/88f6d0021ed594b5d0a3efe6285f8379858fd039 which is not yet merged into main (>v4.0.0).

# Single-File Targeted Search
The script in [src/targeted_search_for_standards.py](src/targeted_search_for_standards.py) now processes one `.raw` file per run and writes a CSV of matched observed features.

For compounds with multiple matched features in tolerance, output keeps only the single highest-intensity feature per `compound_name`.

Optional trace export can write an MS1-only table with one row per MS1 scan and columns: `time`, `tic`, and one EIC column per final mass feature.

MS1 trace-table saving is automatic (same basename as output CSV with `.ms1_traces.csv`).

## Required Standards CSV Columns
The standards file must contain these columns:

- `compound_name`
- `ion_type`
- `mz`
- `retention_time`
- `polarity`

## Run

```bash
python src/targeted_search_for_standards.py
```

Edit paths/thresholds/plot toggles in the `__main__` block before running.

## Watcher Integration Contract
One invocation processes exactly one `.raw` and writes exactly one output CSV. A future watcher can call this script/function once for each new file.

# Class-Based Pipeline (Watcher + Synthesizer)
The repository now includes a class-based runtime pipeline that:

1. Polls configured raw directories for stable new `.raw` files.
2. Processes each file with `process_raw_to_observed_features_df`.
3. Persists state to `pipeline_manifest.json` in the configured output directory to prevent duplicate processing.
4. Regenerates a single aggregate HTML dashboard when new outputs are written.

## Pipeline Entrypoint

```bash
python src/pipeline.py --mode watch --config data/pipeline_config.example.json
```

One-shot watch loop (useful for cron/systemd testing):

```bash
python src/pipeline.py --mode watch --config data/pipeline_config.example.json --once
```

Force reprocess previously completed files in watch mode:

```bash
python src/pipeline.py --mode watch --config data/hilic_pipeline_config.json --once --force-reprocess
```

Manual one-file processing through orchestrator + synthesis:

```bash
python src/pipeline.py --mode process --config data/pipeline_config.example.json --raw data/raw_positive/your_file.raw
```

## Required Config
Pipeline execution requires `--config` JSON input. Start from:

- `data/pipeline_config.example.json`

Then run:

```bash
python src/pipeline.py --mode watch --config data/hilic_pipeline_config.json
```

### Optional sample gating (pipeline-level)

Use `watcher.sample_name_regex` to process only sample files whose raw filename stem
matches a regex pattern.

- Matching target: raw filename stem (without `.raw`)
- Scope: pipeline-level (non-matching files are ignored, not processed)
- Applies to both `--mode watch` and `--mode process`

Example:

```json
"watcher": {
	"raw_dir": "data/raw_positive",
	"poll_interval_sec": 10.0,
	"stability_wait_sec": 20.0,
	"sample_name_regex": "Pos-(02|03)_"
}
```

## Outputs

- Match CSVs and trace CSVs in configured output directory.
- State manifest JSON at `<output_dir>/pipeline_manifest.json`.
- Compound index at `<output_dir>/dashboard.html`.
- One page per detected compound at `<output_dir>/compounds/<compound-slug>.html`.

## Compound Dashboard Layout

The landing dashboard now lists detected compounds and links to a per-compound page.

Above the compound index table, the landing page includes two QC summary plots:

1. m/z window vs ppm error range per compound
2. RT window vs RT error range per compound

For each compound, bars show tolerance-window x-range and historical error min/max y-range.
The strict global newest sample is overlaid as a dot when that compound is present in that sample.

Each compound page contains 4 plots:

1. x = sample, y = observed m/z
2. x = sample, y = observed retention time
3. x = sample, y = intensity
4. all-sample EIC overlay (most recent sample rendered darkest)

Sample order is acquisition-time chronological (oldest to newest).

## Acquisition-Time Requirement

Processing now requires acquisition/creation time from CoreMS metadata.

- If acquisition time is missing for a new sample, processing fails and the sample is marked failed in the manifest.
- Synthesizer skips legacy sample outputs that do not include acquisition time.