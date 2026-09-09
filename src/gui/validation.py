"""Form validation and config resolution for the MetabWatch GUI.

Pure functions (no tkinter) so unit tests can run without a display.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from metabwatch.config import POLARITIES, PipelineConfig, load_pipeline_config
from metabwatch.presets import METHOD_KEYS, PRESET_SPECS, build_pipeline_config

ConfigSource = Literal["preset", "json"]

SAMPLE_FILTER_LABELS = {
    "targeted": "QC_Metab_(.+)",
    "untargeted": "Pool (case-insensitive)",
}


@dataclass(frozen=True)
class GuiRunRequest:
    """User choices from the GUI form before config resolution."""

    source: ConfigSource
    method: str | None = None
    search: str | None = None
    polarity: str | None = None
    project_id: str | None = None
    input_folder: str | None = None
    output_folder: str | None = None
    config_path: str | None = None
    once: bool = False
    force_reprocess: bool = False


def preset_summary_text(method: str, search: str) -> str:
    """Return a one-line description of built-in preset defaults."""
    spec = PRESET_SPECS.get(method.lower(), PRESET_SPECS["hilic_metab_pnnl"])
    filt = SAMPLE_FILTER_LABELS.get(search.lower(), SAMPLE_FILTER_LABELS["targeted"])
    rt = spec["rt_tolerance"]
    rt_text = str(int(rt)) if float(rt).is_integer() else str(rt)
    area = spec["min_area"]
    area_text = str(int(area)) if float(area).is_integer() else str(area)
    return (
        f"Defaults: m/z {spec['mz_tolerance_ppm']:g} ppm · "
        f"RT {rt_text} min · "
        f"min area {area_text} · "
        f"sample filter: {filt}"
    )


def validate_request(req: GuiRunRequest) -> str | None:
    """Return an error message if the request is invalid, else None."""
    if req.source == "preset":
        if not req.method or req.method not in METHOD_KEYS:
            return "Select a method (PNNL Standard HILIC or RP Metabolomics)."
        if not req.search or req.search not in {"targeted", "untargeted"}:
            return "Select a search mode (Targeted or Untargeted)."
        polarity_key = (req.polarity or "auto").strip().lower()
        if polarity_key not in {"auto", *POLARITIES}:
            return "Select a polarity (Auto, Positive, or Negative)."
        input_text = (req.input_folder or "").strip()
        output_text = (req.output_folder or "").strip()
        if not input_text:
            return "Input folder is required."
        if not output_text:
            return "Output folder is required."
        input_path = Path(input_text).expanduser()
        if not input_path.is_dir():
            return f"Input folder does not exist or is not a directory:\n{input_path}"
        return None

    if req.source == "json":
        config_text = (req.config_path or "").strip()
        if not config_text:
            return "Config file path is required."
        config_path = Path(config_text).expanduser()
        if not config_path.is_file():
            return f"Config file not found:\n{config_path}"
        if config_path.suffix.lower() != ".json":
            return "Config file must be a .json file."
        return None

    return f"Unknown config source: {req.source!r}"


def resolve_config(req: GuiRunRequest) -> PipelineConfig:
    """Build a PipelineConfig from a validated GuiRunRequest.

    Raises
    ------
    ValueError
        If validation fails or the config cannot be loaded/built.
    """
    error = validate_request(req)
    if error:
        raise ValueError(error)

    if req.source == "json":
        return load_pipeline_config(Path(req.config_path.strip()).expanduser())

    assert req.method is not None
    assert req.search is not None
    assert req.input_folder is not None
    assert req.output_folder is not None
    polarity_key = (req.polarity or "auto").strip().lower()
    polarity = None if polarity_key == "auto" else polarity_key
    return build_pipeline_config(
        req.method,
        req.search,
        Path(req.input_folder.strip()).expanduser(),
        Path(req.output_folder.strip()).expanduser(),
        polarity=polarity,
        project_id=req.project_id or "",
    )
