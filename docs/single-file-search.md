# Single-File Targeted Search

Processor module: `src/targeted_search_for_standards.py`

This module processes one Thermo `.raw` file at a time and writes:

- `<sample>_targeted_matches.csv`
- `<sample>_ms1_traces.csv`

When multiple matched features satisfy tolerance for a compound, the output keeps the highest-intensity feature per `compound_name`.

## Standards CSV Requirements

Required columns:

- `compound_name`
- `ion_type`
- `mz`
- `retention_time`
- `polarity`

## Trace Output

MS1 trace output is written automatically. The table includes:

- `time`
- `tic`
- EIC columns for matched mass features
- EIC columns for each target compound (including non-detected compounds)

## Local Script Run

The module includes a `__main__` block for local runs:

```bash
python src/targeted_search_for_standards.py
```

Edit paths and thresholds in the `__main__` block before executing.

## Watcher Contract

Each invocation is one-input/one-output at the sample level:

- one `.raw` in
- one per-sample matches CSV out

This contract is what allows the watcher pipeline to process files independently and safely.