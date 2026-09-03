"""Write a user-owned starter custom JSON plus copies of RP preset assets.

Pure functions (no tkinter) so unit tests can run without a display.
The packaged files under ``src/presets/rp_metab_pnnl/`` are only read, never
modified. Targeted compound lists are a blank header, not a copy of the
packaged RP QC rows.
"""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from metabwatch.presets import _asset_path

CONFIG_FILENAME = "metabwatch_config.json"
COREMS_FILENAME = "corems.toml"
README_FILENAME = "README.md"
PACKAGED_CSV_FILENAME = "qc_compounds.csv"
COMPOUNDS_CSV_FILENAME = "monitored_compounds.csv"
COMPOUNDS_CSV_COLUMNS = (
    "compound_name",
    "ion_type",
    "mz",
    "retention_time",
    "polarity",
)

RP_METHOD = "rp_metab_pnnl"
RP_MZ_TOLERANCE_PPM = 5.0
RP_RT_TOLERANCE = 0.4
RP_MIN_AREA = 20000.0
RP_TOP_N = 100
RP_TARGETED_REGEX = r"QC_Metab_(.+)"
RP_UNTARGETED_REGEX = r"(?i)Pool"
DEFAULT_CONFIG_FOLDER_NAME = "metabwatch_config"
_INVALID_FOLDER_CHARS = set('<>:"/\\|?*')


@dataclass(frozen=True)
class StarterSettings:
    """Fields collected by the starter-folder form."""

    input_folder: Path | str
    output_folder: Path | str
    targeted: bool
    mz_tolerance_ppm: float = RP_MZ_TOLERANCE_PPM
    rt_tolerance: float = RP_RT_TOLERANCE
    min_area: float = RP_MIN_AREA
    sample_name_regex: str = ""
    top_n: int = RP_TOP_N

    def resolved_regex(self) -> str:
        """Return the form regex, or the RP default for the search mode."""
        text = str(self.sample_name_regex or "").strip()
        if text:
            return text
        return default_sample_name_regex(self.targeted)


@dataclass(frozen=True)
class StarterWriteResult:
    """Paths produced by :func:`write_rp_starter_folder`."""

    dest_dir: Path
    config_path: Path
    written: tuple[Path, ...]


def default_sample_name_regex(targeted: bool) -> str:
    """RP preset sample-name regex for targeted or untargeted search."""
    return RP_TARGETED_REGEX if targeted else RP_UNTARGETED_REGEX


def rp_packaged_dir() -> Path:
    """Directory of shipped RP CoreMS / QC files (read-only for this writer)."""
    return _asset_path(RP_METHOD, COREMS_FILENAME).parent


def normalize_config_folder_name(name: str) -> str:
    """Return a single path component for a new config folder."""
    text = str(name or "").strip()
    if not text:
        raise ValueError("Folder name is required.")
    if text in {".", ".."}:
        raise ValueError("Folder name is not valid.")
    if any(char in text for char in _INVALID_FOLDER_CHARS) or Path(text).name != text:
        raise ValueError("Folder name cannot contain slashes or other special characters.")
    return text


def requested_config_dir(parent: Path | str, folder_name: str) -> Path:
    """Return ``parent / folder_name`` after validating both pieces."""
    parent_text = str(parent or "").strip()
    if not parent_text:
        raise ValueError("Save-in folder is required.")
    parent_path = Path(parent_text).expanduser().resolve()
    if not parent_path.is_dir():
        raise ValueError(
            f"Save-in folder does not exist or is not a directory:\n{parent_path}"
        )
    return parent_path / normalize_config_folder_name(folder_name)


def next_available_config_dir(parent: Path | str, folder_name: str) -> Path:
    """Return a new (or empty) folder path under ``parent``.

    If ``parent / folder_name`` is missing or empty, that path is used.
    If it already has files, return ``folder_name_2``, ``folder_name_3``, …
    so an existing config folder is never reused.
    """
    requested = requested_config_dir(parent, folder_name)
    if _dir_is_free(requested):
        return requested
    n = 2
    while True:
        candidate = requested.parent / f"{requested.name}_{n}"
        if _dir_is_free(candidate):
            return candidate
        n += 1


def _dir_is_free(path: Path) -> bool:
    """True when ``path`` does not exist or is an empty directory."""
    if not path.exists():
        return True
    return path.is_dir() and not any(path.iterdir())


def settings_from_form(
    *,
    input_folder: str,
    output_folder: str,
    targeted: bool,
    mz_tolerance_ppm: str,
    rt_tolerance: str,
    min_area: str,
    sample_name_regex: str,
    top_n: str = "",
) -> StarterSettings:
    """Parse starter-form strings into :class:`StarterSettings`.

    Raises
    ------
    ValueError
        If a required path is empty or a numeric field cannot be parsed.
    """
    input_text = input_folder.strip()
    output_text = output_folder.strip()
    if not input_text:
        raise ValueError("Input folder is required.")
    if not output_text:
        raise ValueError("Output folder is required.")

    settings = StarterSettings(
        input_folder=input_text,
        output_folder=output_text,
        targeted=bool(targeted),
        mz_tolerance_ppm=_parse_float(mz_tolerance_ppm, "m/z tolerance"),
        rt_tolerance=_parse_float(rt_tolerance, "RT tolerance"),
        min_area=_parse_float(min_area, "Minimum peak area"),
        sample_name_regex=sample_name_regex.strip(),
        top_n=_parse_int(top_n, "Top N peaks") if not targeted else RP_TOP_N,
    )
    validate_starter_settings(settings)
    return settings


def validate_starter_settings(settings: StarterSettings) -> None:
    """Raise ``ValueError`` if settings cannot be written as valid JSON."""
    if not str(settings.input_folder).strip():
        raise ValueError("Input folder is required.")
    if not str(settings.output_folder).strip():
        raise ValueError("Output folder is required.")
    if settings.mz_tolerance_ppm <= 0:
        raise ValueError("m/z tolerance must be greater than 0.")
    if settings.rt_tolerance <= 0:
        raise ValueError("RT tolerance must be greater than 0.")
    if settings.min_area < 0:
        raise ValueError("Minimum peak area must be 0 or greater.")
    if not settings.targeted and int(settings.top_n) <= 0:
        raise ValueError("Top N peaks must be greater than 0.")
    regex = settings.resolved_regex()
    if not regex:
        raise ValueError("Sample-name filter is required.")
    try:
        re.compile(regex)
    except re.error as exc:
        raise ValueError(f"Sample-name filter is not a valid regex: {exc}") from exc


def blank_compounds_csv_text() -> str:
    """Return a header-only standards CSV (no default compound rows)."""
    return ",".join(COMPOUNDS_CSV_COLUMNS) + "\n"


def starter_readme_text(targeted: bool) -> str:
    """Return operator instructions for a newly written starter folder."""
    columns = ",".join(COMPOUNDS_CSV_COLUMNS)
    if targeted:
        compounds_section = f"""\
## Fill the compound list before you Start

`{COMPOUNDS_CSV_FILENAME}` is a blank template. Add one row per compound in
Excel or a text editor. Keep the header row. Do not start a targeted run until
this file has at least one compound for the polarity you are acquiring
(`positive` or `negative`). An empty list fails when the first sample is
processed.

Required columns (in this order):

```
{columns}
```

Example row:

```
Caffeine,[M+H]+,195.0877,4.20,positive
```

- `polarity` must be `positive` or `negative` (lowercase).
- `mz` and `retention_time` (minutes) must be numbers.
- `ion_type` is a label such as `[M+H]+` or `[M-H]-`.
- Do not put comment lines in the CSV.

This file is not a copy of the packaged RP QC list. If you want those rows as
a starting point, copy them from the packaged RP `qc_compounds.csv` yourself.
"""
        files_row = (
            f"| `{COMPOUNDS_CSV_FILENAME}` | Compound list for targeted search "
            "(header only until you add rows) |\n"
        )
        next_steps = f"""\
1. Open `{COMPOUNDS_CSV_FILENAME}` and add your compounds (see below).
2. Optionally edit `{COREMS_FILENAME}` if you need different CoreMS settings.
   It is a copy of the PNNL Standard RP Metabolomics method.
3. In MetabWatch, Config source should already be **Custom JSON** pointing at
   `{CONFIG_FILENAME}`. Click **Start**.
4. To reuse later: Custom JSON → Browse → this `{CONFIG_FILENAME}`.
"""
    else:
        compounds_section = """\
## Untargeted search

This config is untargeted, so there is no compound list in this folder. The
first sample that matches the sample-name filter builds the search space
(`untargeted_search_space.csv` under the output folder). Later samples are
matched against that list.
"""
        files_row = ""
        next_steps = f"""\
1. Optionally edit `{COREMS_FILENAME}` if you need different CoreMS settings.
   It is a copy of the PNNL Standard RP Metabolomics method.
2. In MetabWatch, Config source should already be **Custom JSON** pointing at
   `{CONFIG_FILENAME}`. Click **Start**.
3. To reuse later: Custom JSON → Browse → this `{CONFIG_FILENAME}`.
"""

    return f"""\
# MetabWatch custom config

This folder was created by **Create custom config** in the MetabWatch GUI.
Edit the files here. Packaged presets that ship with MetabWatch are not
changed.

## What to do next

{next_steps}
## Files

| File | Purpose |
|------|---------|
| `{CONFIG_FILENAME}` | Pipeline settings (folders, tolerances, targeted vs untargeted) |
| `{COREMS_FILENAME}` | CoreMS processing parameters (RP starter copy) |
{files_row}| `{README_FILENAME}` | These instructions |

{compounds_section}
## Other notes

- Paths in `{CONFIG_FILENAME}` are absolute. If you move this folder, update
  `corems_params` and (when targeted) `qc_compounds`. Update `input_folder`
  and `output_folder` if those locations changed.
- The sample-name filter is the JSON key `sample_name_regex`.
- CLI equivalent: `metabwatch --config {CONFIG_FILENAME}` from a working
  directory that can see those paths (absolute paths still work from anywhere).
"""


def build_starter_payload(dest_dir: Path, settings: StarterSettings) -> dict[str, Any]:
    """Return the simplified-schema object that will be written as JSON."""
    dest = Path(dest_dir).expanduser().resolve()
    payload: dict[str, Any] = {
        "input_folder": str(Path(settings.input_folder).expanduser().resolve()),
        "output_folder": str(Path(settings.output_folder).expanduser().resolve()),
        "corems_params": str((dest / COREMS_FILENAME).resolve()),
        "targeted": bool(settings.targeted),
        "sample_name_regex": settings.resolved_regex(),
        "mz_tolerance_ppm": float(settings.mz_tolerance_ppm),
        "rt_tolerance": float(settings.rt_tolerance),
        "min_area": float(settings.min_area),
    }
    if settings.targeted:
        payload["qc_compounds"] = str((dest / COMPOUNDS_CSV_FILENAME).resolve())
    else:
        payload["top_n"] = int(settings.top_n)
    return payload


def write_rp_starter_folder(
    dest_dir: Path | str,
    settings: StarterSettings,
    *,
    overwrite: bool = False,
) -> StarterWriteResult:
    """Copy the RP CoreMS TOML into ``dest_dir`` and write starter files.

    Targeted folders get a header-only ``monitored_compounds.csv`` (no packaged
    RP compound rows). Every folder gets ``README.md`` with operator steps.

    Parameters
    ----------
    dest_dir
        Folder that will own the JSON and starter files. Created if missing.
    settings
        Pipeline folders, search mode, and tolerances from the form.
    overwrite
        When false (default), refuse to replace existing starter filenames.

    Returns
    -------
    StarterWriteResult
        Destination folder, JSON path, and the files that were written.

    Raises
    ------
    ValueError
        Invalid settings, or ``dest_dir`` is the packaged RP preset folder.
    FileExistsError
        A starter filename already exists and ``overwrite`` is false.
    FileNotFoundError
        A packaged RP asset is missing from the install.
    """
    validate_starter_settings(settings)

    dest = Path(dest_dir).expanduser().resolve()
    packaged = rp_packaged_dir().resolve()
    if dest == packaged:
        raise ValueError("Refusing to write into the packaged RP preset folder.")
    if dest.exists() and not dest.is_dir():
        raise ValueError(f"Starter destination is not a directory:\n{dest}")

    planned = [dest / CONFIG_FILENAME, dest / COREMS_FILENAME, dest / README_FILENAME]
    if settings.targeted:
        planned.append(dest / COMPOUNDS_CSV_FILENAME)
    existing = [path for path in planned if path.exists()]
    if existing and not overwrite:
        names = ", ".join(path.name for path in existing)
        raise FileExistsError(f"Config files already exist in {dest}: {names}")

    dest.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []
    toml_dest = dest / COREMS_FILENAME
    shutil.copy2(_asset_path(RP_METHOD, COREMS_FILENAME), toml_dest)
    written.append(toml_dest)
    if settings.targeted:
        csv_dest = dest / COMPOUNDS_CSV_FILENAME
        csv_dest.write_text(blank_compounds_csv_text(), encoding="utf-8")
        written.append(csv_dest)

    readme_path = dest / README_FILENAME
    readme_path.write_text(starter_readme_text(settings.targeted), encoding="utf-8")
    written.append(readme_path)

    config_path = dest / CONFIG_FILENAME
    payload = build_starter_payload(dest, settings)
    config_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    written.append(config_path)

    return StarterWriteResult(
        dest_dir=dest,
        config_path=config_path,
        written=tuple(written),
    )


def _parse_float(text: str, label: str) -> float:
    raw = str(text).strip()
    if not raw:
        raise ValueError(f"{label} is required.")
    try:
        return float(raw)
    except ValueError as exc:
        raise ValueError(f"{label} must be a number.") from exc


def _parse_int(text: str, label: str) -> int:
    raw = str(text).strip()
    if not raw:
        raise ValueError(f"{label} is required.")
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{label} must be a whole number.") from exc
    return value
