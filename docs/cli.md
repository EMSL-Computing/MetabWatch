# Command line

Use this page when you run **metabwatch** in a terminal. For the window, see the
[README](../README.md). For Windows setup, see [Windows install](INSTALL.md).

After `pip install -e .` from the repo root:

## Preset run

```bash
metabwatch --method hilic_metab_pnnl --search targeted \
  --input /path/to/raw_folder \
  --output /path/to/results
```

| Flag | Values | Meaning |
|------|--------|---------|
| `--method` | `hilic_metab_pnnl`, `hilic_metab_olympic_eclipse01`, `rp_metab_pnnl`, `rp_metab_olympic_eclipse01` | Packaged method (CoreMS settings + QC list). Olympic / Eclipse 01 keys use a tighter RT window. |
| `--search` | `targeted`, `untargeted` | Targeted matches the packaged QC list. Untargeted builds a list from the first matching file. |
| `--polarity` | `positive`, `negative` | Optional. Locks the results folder before the first sample. Omit to lock from the first successful file. |
| `--project-id` | text | Optional. Only process files whose name contains this text (not case-sensitive). The method’s sample-name filter still applies. |
| `--input` / `-i` | path | Folder of Thermo `.raw` files |
| `--output` / `-o` | path | Results folder |

Do not combine these flags with `--config`.

Also: `--once` (process what is already there, then exit), `--force-reprocess`
(run again even if the file was already done), `--mode process --raw <file.raw>`
(one explicit file). Default mode is watch (keep looking for new files).

### Method defaults

| `--method` | Display name | m/z ppm | RT (min) | min area | Sample-name filter |
|------------|--------------|---------|----------|----------|--------------------|
| `hilic_metab_pnnl` | PNNL Standard HILIC Metabolomics Method | 5 | 0.8 | 1000 | Targeted: `QC_Metab_(.+)` · Untargeted: `Pool` (case-insensitive) |
| `hilic_metab_olympic_eclipse01` | PNNL Standard HILIC — Olympic LC / Eclipse 01 | 5 | 0.6 | 1000 | same |
| `rp_metab_pnnl` | PNNL Standard RP Metabolomics Method | 5 | 0.4 | 20000 | same |
| `rp_metab_olympic_eclipse01` | PNNL Standard RP — Olympic LC / Eclipse 01 | 5 | 0.2 | 20000 | same |

```bash
metabwatch --method hilic_metab_pnnl --search targeted -i RAW -o OUT --once
metabwatch --method hilic_metab_pnnl --search targeted -i RAW -o OUT --once --force-reprocess
metabwatch --method hilic_metab_pnnl --search targeted -i RAW -o OUT \
  --mode process --raw /path/to/file.raw
```

## JSON config

For a custom compound list, tolerances, or CoreMS file:

```bash
metabwatch --config path/to/metabwatch_config.json
```

The GUI **Create custom config** button writes this shape. Edit keys in the
folder’s `README.txt` for operator help; this section is the field list.

### Required

| Field | Meaning |
|-------|---------|
| `input_folder` | Folder of Thermo `.raw` files |
| `output_folder` | Results folder |
| `corems_params` | Path to a CoreMS TOML |
| `targeted` | `true` = compound list; `false` = untargeted |
| `sample_name_regex` | Pattern the file name (without `.raw`) must match |
| `qc_compounds` | Path to the compound CSV (**required when `targeted` is `true`**) |

### Optional (people actually edit these)

| Field | Default | Meaning |
|-------|---------|---------|
| `mz_tolerance_ppm` | `5.0` | How close mass must be (ppm) |
| `rt_tolerance` | `0.5` | How close retention time must be (minutes) |
| `min_area` | `5000` | Ignore smaller peaks |
| `top_n` | `100` | How many largest peaks to keep when untargeted |
| `polarity` | unset | `positive` or `negative`. Omit to lock from the first successful file. |
| `project_id` | `""` | Extra file-name substring filter. Empty = no extra filter. |

Leave `poll_interval_sec`, `stability_wait_sec`, `discovery_mode`, retries, and
plot flags at defaults unless you have a reason.

### Compound CSV columns (targeted)

`compound_name,ion_type,mz,retention_time,polarity`

Example: `Caffeine,[M+H]+,195.0877,4.20,positive`

`polarity` is `positive` or `negative`. `ion_type` must include `+` or `-`.

### Example

```json
{
  "input_folder": "data/raw_positive",
  "output_folder": "data/results_hilic_pos",
  "corems_params": "src/presets/hilic_metab_pnnl/corems.toml",
  "targeted": true,
  "qc_compounds": "src/presets/hilic_metab_pnnl/qc_compounds.csv",
  "sample_name_regex": "QC_Metab_(.+)",
  "mz_tolerance_ppm": 5.0,
  "rt_tolerance": 0.8,
  "min_area": 1000
}
```

Untargeted: set `"targeted": false`, omit `qc_compounds`, add `"top_n": 100` and
a pool filter such as `"(?i)Pool"`. The first matching file builds
`untargeted_search_space.csv` in the results folder (largest `top_n` peaks).
Later files reuse that list. Delete the CSV to rebuild.

## One polarity per results folder

Set `--polarity` / JSON `polarity`, or leave unset (Auto). One output folder is
one polarity. Opposite-polarity files are skipped. If polarity was set up front,
matching files in the same batch still run. If polarity is Auto, a mixed batch
stops after the first mismatch. Use separate input and output folders for
positive and negative.

## Results

The results root is the dashboard and summaries. Per-sample files go in
subfolders (`matches/`, `traces/`). Older runs with those files in the root are
moved on the next process or dashboard rebuild.

- `dashboard.html` (waiting page at run start; plots work offline)
- `compounds/` (one HTML page per compound)
- `matches/*_targeted_matches.csv`
- `traces/*_ms1_traces.csv`, `traces/*_tic.png`
- `export_mz.csv`, `export_rt.csv`, `export_height.csv`, `export_area.csv`
- `pipeline_manifest.json`
- `untargeted_search_space.csv` (untargeted only)

## Old JSON files

Configs with nested `processor` / `watcher` / `synthesizer` / `search_space`
still load. Do not mix old and new keys in one file.

| Old key | New key |
|---------|---------|
| `watcher.raw_dir` | `input_folder` |
| `processor.output_dir` | `output_folder` |
| `processor.params_path` | `corems_params` |
| `processor.standards_csv` | `qc_compounds` |
| `search_space.mode` | `targeted` (`true` / `false`) |
| `watcher.sample_name_regex` | `sample_name_regex` |

## Developers

```bash
make test-unit
make test-workflow-targeted
make test-workflow-untargeted
make test-workflow
make help
```

Thermo `.raw` fixtures go in `data/raw_positive/` (gitignored). See `data/README.md`.
