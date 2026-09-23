"""Peek Thermo .raw polarity from a CoreMS scan filter without loading MS1."""

from __future__ import annotations

from pathlib import Path

_POLARITY_BY_MODE = {1: "positive", -1: "negative"}


def is_polarity_mismatch_error(error: str | None) -> bool:
    """Return True when an error message indicates a polarity lock failure."""
    return bool(error) and "polarity mismatch" in error.lower()


def polarity_from_scan_filter(parser) -> str:
    """Return ``positive`` or ``negative`` from the first scan's Thermo filter.

    Uses CoreMS ``get_polarity_mode(start_scan)`` (one scan-event string),
    not ``get_lcms_obj``, which loads MS1 spectra.
    """
    mode = parser.get_polarity_mode(parser.start_scan)
    polarity = _POLARITY_BY_MODE.get(mode)
    if polarity is None:
        raise ValueError(f"Unknown CoreMS polarity mode {mode!r}")
    return polarity


def polarity_from_lcms(lcms_obj) -> str:
    """Normalized CoreMS polarity on a loaded LCMS object."""
    return str(lcms_obj.polarity).strip().lower()


def skip_if_locked_polarity_mismatch(
    parser,
    raw_file: Path,
    expected_polarity: str | None,
) -> None:
    """Raise the usual polarity-mismatch error before MS1 load when locked.

    No-op when ``expected_polarity`` is unset (Auto: first successful file
    still locks the run). On mismatch, close the Thermo reader if possible.
    After a successful ``get_lcms_obj``, CoreMS already rejects mixed-polarity
    files, so callers should not repeat this check against ``lcms_obj.polarity``.
    """
    if expected_polarity is None:
        return
    expected = str(expected_polarity).strip().lower()
    actual = polarity_from_scan_filter(parser)
    if actual == expected:
        return
    close = getattr(parser, "close_file", None)
    if callable(close):
        try:
            close()
        except Exception:
            pass
    raise ValueError(
        f"Polarity mismatch: file {raw_file.name} is '{actual}' "
        f"but this run is locked to '{expected}'. "
        "MetabWatch does not allow mixed polarities in one input folder / run."
    )
