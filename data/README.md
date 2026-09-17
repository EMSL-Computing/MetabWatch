# `data/`

Local fixtures and source lists. Packaged methods live in `src/presets/`, not here.

## Tracked

| File | What it is |
|------|------------|
| `original_QC_list.xlsx` | Source HILIC QC list (W. Kew, April 2026) |
| `QC_Metab_26-06.csv` | Olympic LC / Eclipse 01 QC list (Priscila Lalli, 26 August 2026). Packaged HILIC/RP search spaces use these retention times: omit a compound when this list has no numeric RT for that method, and omit an ion type when `[M+H]+` or `[M-H]-` is not numeric. HILIC targeted lists also omit Hesperetin (both polarities), Syringaldehide (both polarities), and L-Glutamine (negative only). |

## Local only (not in git)

| Path | What it is |
|------|------------|
| `raw_positive/`, `raw_negative/`, `raw_mixed/` | Thermo `.raw` fixtures for `make test-workflow-*` |
| `results_*` | Pipeline outputs from those smoke runs |

## Related, not in this folder

- Packaged CoreMS TOMLs and QC CSVs: `src/presets/<method>/`
- Untargeted Makefile smoke JSON (`QC_Metab_*` sample filter): `tests/data/hilic_pipeline_config_untargeted.json`
