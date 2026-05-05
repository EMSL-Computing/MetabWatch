# LCMS QC
This repository contains scripts for performing quality control (QC) on liquid chromatography-mass spectrometry (LCMS) data using the CoreMS software.  The scripts are designed to process raw LCMS data files, perform a targeted search for specific compounds.

# CoreMS
This uses a DEVELOPMENT version of CoreMS available at https://github.com/EMSL-Computing/CoreMS/commit/88f6d0021ed594b5d0a3efe6285f8379858fd039 which is not yet merged into main (>v4.0.0).  We recommend using the Docker approach above since it will ensure the correct version of CoreMS is used and will handle the installation of CoreMS, its dependencies, and some tricky dependencies needed to read .raw files (e.g., Thermo .raw files).

# Single-File Targeted Search
The script in [src/targeted_search_for_standards.py](src/targeted_search_for_standards.py) now processes one `.raw` file per run and writes a CSV of matched observed features.

For compounds with multiple matched features in tolerance, output keeps only the single highest-intensity feature per `compound_name`.

## Required Standards CSV Columns
The standards file must contain these columns:

- `compound_name`
- `ion_type`
- `mz`
- `retention_time`
- `polarity`

## Example Command

```bash
python src/targeted_search_for_standards.py \
	--raw_file data/raw_positive/QC_Metab_25-02_Monet_HILIC_Pos-01B_26Dec25_Olympic_WBEH-9262_RR.raw \
	--standards_csv data/qc_search_space/hilic_qc_search.csv \
	--params_path data/corems_params/monet_hilic_corems_lcms_params.toml \
	--output_csv data/results_hilic_pos01.csv \
	--mz_tolerance_ppm 5.0 \
	--rt_tolerance 0.5 \
	--min_area 10000 \
	--plot_eics \
	--plot_pdf data/results_hilic_pos01_eics.pdf \
	--plot_tic \
	--tic_png data/results_hilic_pos01_tic.png
```

## Watcher Integration Contract
One invocation processes exactly one `.raw` and writes exactly one output CSV. A future watcher can call this script/function once for each new file.