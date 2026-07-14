# Pipeline Reference

## Entrypoint

```bash
python src/pipeline.py --mode watch --config <config.json>
```

Modes:

- `watch`: poll for stable `.raw` files and process continuously
- `process`: process one explicit file via `--raw`

## Example Commands

Watch mode:

```bash
python src/pipeline.py --mode watch --config data/hilic_pipeline_config.json
```

One-shot watch loop:

```bash
python src/pipeline.py --mode watch --config data/hilic_pipeline_config.json --once
```

Force reprocess:

```bash
python src/pipeline.py --mode watch --config data/hilic_pipeline_config.json --once --force-reprocess
```

Single-file process mode:

```bash
python src/pipeline.py --mode process --config data/hilic_pipeline_config.json --raw data/raw_positive/your_file.raw
```

## Config Structure

Top-level sections:

- `processor`
- `watcher`
- `synthesizer`
- `search_space` (optional; controls targeted vs. untargeted mode — see below)
- retry settings (`max_retries`, `initial_backoff_sec`, `backoff_multiplier`)
- stale-state setting (`stale_in_progress_sec`)

Important watcher fields:

- `raw_dir`: input directory to poll
- `poll_interval_sec`: poll period
- `stability_wait_sec`: how long file must remain unchanged
- `sample_name_regex` (optional): process only matching filename stems

Example watcher section:

```json
"watcher": {
  "raw_dir": "data/raw_positive",
  "poll_interval_sec": 10.0,
  "stability_wait_sec": 20.0,
  "sample_name_regex": "Pos-(02|03)_"
}
```

## Search-Space Modes

By default the pipeline runs in `targeted` mode against `processor.standards_csv`. To run untargeted instead, add a `search_space` block:

```json
"search_space": {
  "mode": "untargeted",
  "top_n": 100
}
```

In untargeted mode:

- The first sample matching `watcher.sample_name_regex` triggers CoreMS untargeted peak picking + integration; the top `top_n` peaks (ranked by integrated area, descending) are written to `<output_dir>/untargeted_search_space.csv`.
- The same sample is then processed against that CSV (so it shows up in the dashboard like every other sample).
- All subsequent samples reuse the persisted CSV.
- `processor.standards_csv` is optional in this mode.
- Re-bootstrap is manual: delete `untargeted_search_space.csv` and rerun.
- Bootstrap failures count toward `max_retries` (same cap as per-sample processing). After exhausting retries the file is marked failed and skipped on subsequent polls.

When omitted, `search_space` defaults to `{"mode": "targeted", "top_n": 100}`.

## Runtime Behavior

The pipeline:

1. Discovers stable new `.raw` files.
2. Queues work with deduplication.
3. Processes each file with retry/backoff.
4. Writes/updates `pipeline_manifest.json` for idempotency.
5. Rebuilds the HTML dashboard when new output appears.

## Output Artifacts

- `*_targeted_matches.csv`
- `*_ms1_traces.csv`
- `dashboard.html`
- `compounds/<compound-slug>.html`
- `export_mz.csv`, `export_rt.csv`, `export_height.csv` (wide pivots: one row per mass feature, one column per sample)
- `pipeline_manifest.json`
- `untargeted_search_space.csv` (untargeted mode only — generated from the first matching sample, reused on subsequent runs)

## Acquisition-Time Requirement

- New samples must provide parseable acquisition time from CoreMS metadata.
- If acquisition time is missing, processing fails and the file is marked failed in the manifest.
- Dashboard synthesis skips legacy outputs lacking acquisition time.