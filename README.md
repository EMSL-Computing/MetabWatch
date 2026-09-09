# MetabWatch

**MetabWatch** watches a folder of Thermo `.raw` files, matches QC compounds
(or a peak list from the first matching sample), and refreshes an HTML dashboard.

Lab use is the **MetabWatch** window. Command line: [docs/cli.md](docs/cli.md).

## Open MetabWatch

### **Windows (recommended):** 

Double-click the desktop shortcut (named with the version,
e.g. `MetabWatch 0.3.0`), or `Start-MetabWatch.ps1` in the repo folder.

Or run `metabwatch-gui` from the command line within an appropriately configured Python environment.

Instructions for **Windows** installation: [Windows install](docs/INSTALL.md).

### **macOS (developers only):**

Lab use is Windows. macOS is for developers only. Run `metabwatch-gui`
from a configured Python environment. Setup: [Maintainer / development](docs/MAINTAINER.md)
(points at [CoreMS](https://github.com/EMSL-Computing/CoreMS) for Thermo `.raw` / pythonnet).

## Quick Start (from GUI)

1. **Choose Preset Method** — packaged HILIC or RP method.
2. **Search** — Targeted (packaged QC list) or Untargeted (peak list from the
   first matching sample).
3. **Polarity** — Auto (detects from first sample and locks in the rest), Positive, or Negative.
4. **Project ID** (optional) — only files whose name contains this text.
5. **Input folder** / **Output folder**.
6. **Process once** (what is already there) or **Watch continuously** (new files
   until Stop).
7. **Start**.
8. **Open dashboard**

### What the options mean

- **Targeted** matches the method’s compound list. **Untargeted** builds a list
  from the first sample whose name matches the usual filter (`QC_Metab_` or
  `Pool`).
- **Polarity:** Auto locks from the first successful file; Positive/Negative
  lock before the first sample. One polarity per output folder.
- **Project ID:** extra file-name filter. Leave empty to keep only the usual
  sample filter.
- **Force reprocess:** run again even if that file was already done.

Do not mix positive and negative into one output folder. If polarity is set up
front, matching files in a mixed input folder still run. If polarity is Auto, a
mixed batch stops after the first mismatch.

## Custom compound list

**Create custom config** writes a new folder (`metabwatch_config`, or `_2` if
that name is taken) with JSON, a copy of CoreMS settings, a `README.txt`,
and (targeted) a blank `monitored_compounds.csv`. Existing folders are not
overwritten. *Fill the CSV of monitored_compounds before a targeted Start for targeted runs*. More details can be found in folder’s `README.txt`.

## Results

- `dashboard.html` — compound table and plots (offline; no internet needed)
- `compounds/` — one page per compound
- `matches/` — per-sample match CSVs
- `traces/` — per-sample MS1 traces and TIC plots
- `export_mz.csv`, `export_rt.csv`, `export_height.csv`, `export_area.csv`

## More

- [Windows install](docs/INSTALL.md) — lab PC, shortcut
- [Command line](docs/cli.md) — `metabwatch` flags and JSON
- [Maintainer / development](docs/MAINTAINER.md) — Python, macOS, CoreMS
- [Changelog](docs/CHANGELOG.md)
