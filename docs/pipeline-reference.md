# Pipeline Reference

**MetabWatch** package name: `metabwatch` (CLI: `metabwatch`).

## Dependencies

Runtime dependencies are declared in `pyproject.toml`. The pipeline requires **CoreMS 4.0.1** for:

- Thermo `.raw` file reading (`ImportMassSpectraThermoMSFileReader`)
- LC-MS parameter loading from TOML (`load_and_set_toml_parameters_lcms`)
- Targeted mass-feature detection / integration / clustering
- Untargeted peak picking used to bootstrap `untargeted_search_space.csv`

Install with `pip install -e .` from the repository root. Thermo raw support also needs `pythonnet` (and Mono on macOS/Linux); see the main [README](../README.md#corems).

## Entrypoint

After `pip install -e .`:

### Standard path (presets)

```bash
metabwatch --method hilic --search targeted \
  --input /path/to/raw --output /path/to/results
# or short aliases:
metabwatch --method rp --search untargeted -i RAW -o OUT
```

| Flag | Values | Meaning |
|------|--------|---------|
| `--method` | `rp`, `hilic` | Chromatography method (selects CoreMS + QC assets) |
| `--search` | `targeted`, `untargeted` | Search-space mode |
| `--input` / `-i` | path | Folder of Thermo `.raw` files |
| `--output` / `-o` | path | Results folder |

Do **not** combine preset flags with `--config`.

Runtime modes:

- `watch` (default): discover stable `.raw` files and process continuously
- `process`: process one explicit file via `--raw`

### Advanced path (JSON config)

```bash
metabwatch --config <config.json>
# or:
python -m metabwatch.pipeline --config <config.json>
```

Simplified flat JSON and legacy nested schemas are both supported (see below).

## Built-in presets

Assets ship with the package under `metabwatch.presets` (`src/presets/`):

| method | search | CoreMS | QC CSV | sample_name_regex | mz ppm | RT min | min_area |
|--------|--------|--------|--------|-------------------|--------|--------|----------|
| hilic | targeted | `hilic/corems.toml` | `hilic/qc_compounds.csv` | `QC_Metab_(.+)` | 5 | 0.8 | 1000 |
| hilic | untargeted | `hilic/corems.toml` | _(bootstrap)_ | `(?i)Pooled` | 5 | 0.8 | 1000 |
| rp | targeted | `rp/corems.toml` | `rp/qc_compounds.csv` | `QC_Metab_(.+)` | 5 | 0.4 | 20000 |
| rp | untargeted | `rp/corems.toml` | _(bootstrap)_ | `(?i)Pooled` | 5 | 0.4 | 20000 |


## Example Commands

Watch mode (preset):

```bash
metabwatch --method hilic --search targeted -i data/raw_positive -o data/results_hilic_pos
```

One-shot watch loop:

```bash
metabwatch --method hilic --search targeted -i data/raw_positive -o data/results_hilic_pos --once
```

Force reprocess:
Allows reprocessing of previously processed files (overwrites existing results):

```bash
metabwatch --method hilic --search targeted -i data/raw_positive -o data/results_hilic_pos \
  --once --force-reprocess
```

Single-file process mode:

```bash
metabwatch --method hilic --search targeted -i data/raw_positive -o data/results_hilic_pos \
  --mode process --raw data/raw_positive/your_file.raw
```

Advanced JSON:

```bash
metabwatch --config data/hilic_pipeline_config.json
```

## Config Structure (Simplified — Advanced)

Configs use a flat JSON schema. Relative paths resolve against the process working directory (override via ``base_dir`` when loading programmatically).

### Required fields

| Field | Description |
|-------|-------------|
| `input_folder` | Directory to poll for Thermo `.raw` files |
| `output_folder` | Results directory (dashboard, manifest, exports) |
| `corems_params` | Path to CoreMS TOML parameter file |
| `targeted` | `true` for targeted matching; `false` for untargeted bootstrap |
| `sample_name_regex` | Regex applied to the raw filename stem to decide processing |
| `qc_compounds` | Path to standards CSV (**required when `targeted` is `true`**) |

### Optional fields (defaults match the runtime loader)

| Field | Default | Description |
|-------|---------|-------------|
| `mz_tolerance_ppm` | `5.0` | m/z matching tolerance (ppm) |
| `rt_tolerance` | `0.5` | Retention-time tolerance (minutes) |
| `min_area` | `5000` | Minimum peak area |
| `top_n` | `100` | Peaks kept when untargeted |
| `plot_eics` / `plot_tic` | `false` / `true` | Plot flags |
| `integrate_mass_features` | `true` | Run CoreMS peak integration (required for area / Area CV; re-integrates after clustering when both are on) |
| `cluster_mass_features` | `false` | Run CoreMS mass-feature clustering |
| `poll_interval_sec` / `stability_wait_sec` | `10` / `20` | Watcher timing (poll interval / file stability window) |
| `discovery_mode` | `hybrid` | How new `.raw` files are found: `hybrid` (watchdog FS events + periodic full scan), `watchdog` (events + startup scan only), or `poll` (directory scan only) |
| `debounce_sec` | `5.0` | Dashboard rebuild debounce |
| `max_retries` / `initial_backoff_sec` / `backoff_multiplier` | `3` / `10` / `2` | Retry policy |
| `stale_in_progress_sec` | `3600` | Stale in-progress threshold |

### Targeted example

```json
{
  "input_folder": "data/raw_positive",
  "output_folder": "data/results_hilic_pos",
  "corems_params": "src/presets/hilic/corems.toml",
  "targeted": true,
  "qc_compounds": "src/presets/hilic/qc_compounds.csv",
  "sample_name_regex": "QC_Metab_(.+)",
  "mz_tolerance_ppm": 5.0,
  "rt_tolerance": 0.8,
  "min_area": 1000
}
```

### Untargeted example

```json
{
  "input_folder": "data/raw_positive",
  "output_folder": "data/results_hilic_pos_untargeted",
  "corems_params": "src/presets/hilic/corems.toml",
  "targeted": false,
  "sample_name_regex": "QC_Metab_(.+)",
  "top_n": 100
}
```

Derived automatically (never set in JSON):

- `pipeline_manifest.json` and `dashboard.html` under `output_folder`
- Untargeted search-space CSV at `<output_folder>/untargeted_search_space.csv`

## Polarity policy

MetabWatch does **not** allow mixed ionization polarities in one output folder:

1. Polarity is read from CoreMS (`lcms_obj.polarity`) after opening each Thermo `.raw` file.
2. On first successful completion, the polarity is stored in `pipeline_manifest.json` as top-level `"polarity"` (and on that sample’s entry).
3. Later samples pass `expected_polarity` from the manifest into processing; a mismatch fails with a non-retryable `Polarity mismatch` error.
4. In a multi-file batch (bootstrap / `--once` / force-reprocess), remaining files after the first mismatch are **hard-stopped**. With `--once`, the process exits non-zero.
5. In continuous watch mode, a late opposite-polarity drop is rejected, but the watcher keeps running for matching-polarity files.
6. The standards CSV may still list both polarities; only rows matching the sample’s polarity are searched.
7. The dashboard shows **Polarity: …** from the match CSVs. Legacy mixed folders are labeled `mixed (...)` with a warning.

Keep separate `input_folder` / `output_folder` pairs for positive and negative acquisitions.

## Search-Space Modes

- **`targeted: true`** — match against the standards CSV at `qc_compounds`.
- **`targeted: false`** — bootstrap a search space from the first sample matching `sample_name_regex`.

In untargeted mode:

- The first matching sample triggers CoreMS untargeted peak picking + integration; the top `top_n` peaks (ranked by integrated area, descending) are written to `<output_folder>/untargeted_search_space.csv`.
- The same sample is then processed against that CSV (so it shows up in the dashboard like every other sample).
- All subsequent samples reuse the persisted CSV.
- `qc_compounds` is not required in this mode.
- Re-bootstrap is manual: delete `untargeted_search_space.csv` and rerun.
- Bootstrap failures count toward `max_retries` (same cap as per-sample processing). After exhausting retries the file is marked failed and skipped on subsequent polls.

## Legacy Nested Config (Still Supported)

Older configs with nested `processor` / `watcher` / `synthesizer` / `search_space` blocks still load. Do not mix simplified and legacy keys in the same file.

Legacy mapping:

| Legacy key | Simplified key |
|------------|----------------|
| `watcher.raw_dir` | `input_folder` |
| `processor.output_dir` | `output_folder` |
| `processor.params_path` | `corems_params` |
| `processor.standards_csv` | `qc_compounds` |
| `search_space.mode` | `targeted` (`true`/`false`) |
| `watcher.sample_name_regex` | `sample_name_regex` |

Example legacy watcher section:

```json
"watcher": {
  "raw_dir": "data/raw_positive",
  "poll_interval_sec": 10.0,
  "stability_wait_sec": 20.0,
  "discovery_mode": "hybrid",
  "sample_name_regex": "Pos-(02|03)_"
}
```

### Discovery modes

| Mode | Behavior |
|------|----------|
| `hybrid` (default) | `watchdog` filesystem notifications for immediate detection, plus a full directory scan every `poll_interval_sec` as a safety net (useful on NFS/SMB where events can be missed). |
| `watchdog` | FS create/move events only after a **startup reconciliation** scan. No periodic full scan. Stability re-checks on a short tick. |
| `poll` | Legacy behavior: full directory scan each `poll_interval_sec` (no observer). |

In all modes:

- A **startup reconciliation** scan registers `.raw` files that appeared while MetabWatch was not running.
- **Stability** (`stability_wait_sec`) still applies: creation events fire before Thermo has necessarily finished writing the file. Size/mtime must stay unchanged for the stability window before processing.
- `--once` always uses a single full scan and does **not** start the filesystem observer (deterministic smoke runs).

## Runtime Behavior

The pipeline:

1. Discovers new `.raw` candidates (FS events and/or directory scan), then waits until each is **stable**.
2. Queues work with deduplication.
3. Processes each file with retry/backoff.
4. Writes/updates `pipeline_manifest.json` for idempotency.
5. Rebuilds the HTML dashboard when new output appears.

## Output Artifacts

- `*_targeted_matches.csv`
- `*_ms1_traces.csv`
- `dashboard.html`
- `compounds/<compound-slug>.html`
- `export_mz.csv`, `export_rt.csv`, `export_height.csv`, `export_area.csv` (wide pivots: one row per mass feature, one column per sample; area requires `integrate_mass_features`)
- `pipeline_manifest.json`
- `untargeted_search_space.csv` (untargeted mode only — generated from the first matching sample, reused on subsequent runs)

## Acquisition-Time Requirement

- New samples must provide parseable acquisition time from CoreMS metadata.
- If acquisition time is missing, processing fails and the file is marked failed in the manifest.
- Dashboard synthesis skips legacy outputs lacking acquisition time.