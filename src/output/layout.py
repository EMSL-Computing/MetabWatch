"""Where per-sample match/TIC/trace files live in a results folder."""

from __future__ import annotations

from pathlib import Path

MATCHES_DIRNAME = "matches"
TRACES_DIRNAME = "traces"
_MATCH_CSV_SUFFIX = "_targeted_matches.csv"
_TRACE_CSV_SUFFIX = "_ms1_traces.csv"
_TIC_PNG_SUFFIX = "_tic.png"
_EICS_PDF_SUFFIX = "_eics.pdf"
_TRACE_SUFFIXES = (_TRACE_CSV_SUFFIX, _TIC_PNG_SUFFIX, _EICS_PDF_SUFFIX)


def traces_dir(output_dir: Path) -> Path:
    """Return ``<output_dir>/traces``."""
    return Path(output_dir) / TRACES_DIRNAME


def matches_dir(output_dir: Path) -> Path:
    """Return ``<output_dir>/matches``."""
    return Path(output_dir) / MATCHES_DIRNAME


def sample_match_csv(output_dir: Path, stem: str) -> Path:
    """Preferred path for ``<stem>_targeted_matches.csv``."""
    return matches_dir(output_dir) / f"{stem}{_MATCH_CSV_SUFFIX}"


def sample_trace_csv(output_dir: Path, stem: str) -> Path:
    """Preferred path for ``<stem>_ms1_traces.csv``."""
    return traces_dir(output_dir) / f"{stem}{_TRACE_CSV_SUFFIX}"


def sample_tic_png(output_dir: Path, stem: str) -> Path:
    """Preferred path for ``<stem>_tic.png``."""
    return traces_dir(output_dir) / f"{stem}{_TIC_PNG_SUFFIX}"


def sample_eics_pdf(output_dir: Path, stem: str) -> Path:
    """Preferred path for ``<stem>_eics.pdf``."""
    return traces_dir(output_dir) / f"{stem}{_EICS_PDF_SUFFIX}"


def results_root_for(path: Path) -> Path:
    """Return the results folder for a nested or legacy per-sample file."""
    parent = Path(path).parent
    if parent.name in {MATCHES_DIRNAME, TRACES_DIRNAME}:
        return parent.parent
    return parent


def resolve_trace_csv(output_dir: Path, stem: str) -> Path | None:
    """Return an existing traces CSV: ``traces/`` first, then the results root."""
    nested = sample_trace_csv(output_dir, stem)
    if nested.is_file():
        return nested
    legacy = Path(output_dir) / f"{stem}{_TRACE_CSV_SUFFIX}"
    if legacy.is_file():
        return legacy
    return None


def collect_match_csvs(output_dir: Path) -> list[Path]:
    """Match CSVs in ``matches/``, then any leftover files in the results root."""
    root = Path(output_dir)
    found: list[Path] = []
    nested = matches_dir(root)
    if nested.is_dir():
        found.extend(nested.glob(f"*{_MATCH_CSV_SUFFIX}"))
    if root.is_dir():
        found.extend(root.glob(f"*{_MATCH_CSV_SUFFIX}"))
    return sorted(set(found))


def _relocate_suffixes(
    output_dir: Path, dest: Path, suffixes: tuple[str, ...]
) -> list[Path]:
    root = Path(output_dir)
    if not root.is_dir():
        return []
    moved: list[Path] = []
    for path in list(root.iterdir()):
        if not path.is_file():
            continue
        if not path.name.endswith(suffixes):
            continue
        dest.mkdir(parents=True, exist_ok=True)
        target = dest / path.name
        if target.exists():
            path.unlink()
        else:
            path.replace(target)
        moved.append(target)
    return moved


def relocate_legacy_traces(output_dir: Path) -> list[Path]:
    """Move root-level TIC/trace files into ``traces/``."""
    return _relocate_suffixes(output_dir, traces_dir(output_dir), _TRACE_SUFFIXES)


def relocate_legacy_matches(output_dir: Path) -> list[Path]:
    """Move root-level ``*_targeted_matches.csv`` files into ``matches/``."""
    return _relocate_suffixes(
        output_dir, matches_dir(output_dir), (_MATCH_CSV_SUFFIX,)
    )


def relocate_legacy_outputs(output_dir: Path) -> list[Path]:
    """Move root-level per-sample files into ``matches/`` and ``traces/``.

    Exports, the dashboard, Plotly.js, the manifest, and untargeted search-space
    CSV stay in the results root. If a nested file already exists, the root
    copy is removed.
    """
    return relocate_legacy_matches(output_dir) + relocate_legacy_traces(output_dir)
