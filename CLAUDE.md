# CLAUDE.md

LCMS targeted-QC pipeline. Watches a folder for Thermo `.raw` files, runs a per-sample CoreMS targeted search against a standards list, and rebuilds an HTML dashboard.

## Entrypoint

```
python src/pipeline.py --mode {watch|process} --config <config.json> [--raw FILE] [--once] [--force-reprocess]
```

- Watch mode: poll `watcher.raw_dir`, process stable new `.raw` files, rebuild dashboard.
- Process mode: requires `--raw`; processes one file then synthesizes.
- `--once`: single watch iteration (use this for any test run — never start an unbounded `watch` from this session).

Active config: [data/hilic_pipeline_config.json](data/hilic_pipeline_config.json).

## Module layout

All source under [src/](src/), imported as flat top-level packages (no `src.` prefix):

- [src/pipeline.py](src/pipeline.py) — CLI + watch/process loops, retry/backoff, manifest updates, synthesis trigger.
- [src/config.py](src/config.py) — frozen dataclasses (`PipelineConfig`, `ProcessorConfig`, `WatcherConfig`, `StateConfig`, `SynthesizerConfig`) and `load_pipeline_config`. JSON paths are resolved against `repo_root` (the parent of `src/`).
- [src/processor/orchestrator.py](src/processor/orchestrator.py) — `ProcessorOrchestrator`, `ProcessResult`, `RetryPolicy`. Wraps the single-file search.
- [src/targeted_search_for_standards.py](src/targeted_search_for_standards.py) — single-file CoreMS targeted search; one `.raw` in → one `*_targeted_matches.csv` + `*_ms1_traces.csv` out. Keeps highest-intensity feature per `compound_name`.
- [src/watcher/file_watcher.py](src/watcher/file_watcher.py) — `RawFileWatcher`; stability-based polling.
- [src/pipeline_queue/processing_queue.py](src/pipeline_queue/processing_queue.py) — dedup queue.
- [src/state/manifest_store.py](src/state/manifest_store.py) — `ManifestStateStore`; persists `pipeline_manifest.json` (status, attempts, acquisition time). Source of truth for idempotency.
- [src/output/tracker.py](src/output/tracker.py) — `OutputTracker`; debounces synthesis.
- [src/synthesis/synthesizer.py](src/synthesis/synthesizer.py) — `HTMLSynthesizer`; renders `dashboard.html` and per-compound pages from per-sample CSVs. Templates in [src/synthesis/templates/](src/synthesis/templates/).

## Config shape

JSON sections map 1:1 to dataclasses in `src/config.py`. Important details that aren't obvious from the JSON:

- `state.pipeline_manifest` and `synthesizer.html_output` are derived from `processor.output_dir` (`<output_dir>/pipeline_manifest.json`, `<output_dir>/dashboard.html`) — they are **not** configurable in JSON.
- `synthesizer.mz_tolerance_ppm` / `rt_tolerance` are inherited from `processor.*` — single source of truth.
- `watcher.sample_name_regex` is matched with `re.search` against the filename **stem**.
- All relative paths in JSON are resolved against repo root.

## Outputs

Per `processor.output_dir` (e.g. [data/results_hilic_pos/](data/results_hilic_pos/)):

- `<sample>_targeted_matches.csv`, `<sample>_ms1_traces.csv`
- `dashboard.html`, `compounds/<slug>.html`
- `pipeline_manifest.json` (do not hand-edit while watcher is running)

## Acquisition-time requirement

Samples must yield a parseable acquisition time from CoreMS metadata. Missing → marked `failed` in manifest; legacy outputs without it are skipped by the synthesizer. Don't try to back-fill or fake this.

## Conventions

- Python ≥3.10 (uses `str | None`, `list[Path]`).
- `from __future__ import annotations` at top of source files.
- Frozen dataclasses for config; `pathlib.Path` everywhere; numpy-style docstrings.
- No test suite or lint config in the repo — verify changes by running `--mode process` against a single file or `--mode watch --once`.

## CoreMS pin

Depends on the dev commit pinned in [README.md](README.md): `EMSL-Computing/CoreMS@88f6d00`. If CoreMS-side behavior looks off, check that commit before assuming a project bug.

## Things to avoid

- Don't start long-running `watch` mode from this session — use `--once`.
- Don't delete or rewrite `pipeline_manifest.json` to "fix" reprocessing; use `--force-reprocess`.
- Don't add `src.` prefixes to imports — `src/` is on `sys.path` via the entrypoint, not a package.


## Git Rules
- Always pull latest changes before starting work, and check that your branch is up to date with `git status`.
- Use feature branches for new work, and create pull requests for review before merging to main.
- Don't commit large files or any agent-specific documents; these should be kept local and added to `.gitignore` if necessary.
- Agents should never commit to main directly; all changes must go through a PR with human review.