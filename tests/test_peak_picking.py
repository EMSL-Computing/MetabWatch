"""MS1 format check flips CoreMS peak picking (MetaMS behaviour)."""

from __future__ import annotations

from types import SimpleNamespace

import pandas as pd
import pytest

from corems.encapsulation.factory.parameters import LCMSParameters
from metabwatch.processor.peak_picking import (
    CENTROID_PEAK_PICKING,
    PROFILE_PEAK_PICKING,
    align_peak_picking_to_ms1_format,
    ms1_scan_format,
)


def _lcms(ms_format: str | list[str]) -> SimpleNamespace:
    formats = [ms_format, ms_format] if isinstance(ms_format, str) else list(ms_format)
    scan_df = pd.DataFrame(
        {
            "ms_level": [1] * len(formats),
            "ms_format": formats,
        }
    )
    params = LCMSParameters(use_defaults=True)
    params.lc_ms.peak_picking_method = PROFILE_PEAK_PICKING
    return SimpleNamespace(scan_df=scan_df, parameters=params)


def test_ms1_scan_format_profile() -> None:
    assert ms1_scan_format(_lcms("profile")) == "profile"


def test_ms1_scan_format_centroid() -> None:
    assert ms1_scan_format(_lcms("centroid")) == "centroid"


def test_ms1_scan_format_rejects_mix() -> None:
    with pytest.raises(ValueError, match="mix formats"):
        ms1_scan_format(_lcms(["profile", "centroid"]))


def test_align_flips_centroided_ms1_to_centroided_ph() -> None:
    lcms = _lcms("centroid")
    method = align_peak_picking_to_ms1_format(lcms)
    assert method == CENTROID_PEAK_PICKING
    assert lcms.parameters.lc_ms.peak_picking_method == CENTROID_PEAK_PICKING
    assert (
        lcms.parameters.mass_spectrum["ms1"].mass_spectrum.noise_threshold_method
        == "relative_abundance"
    )


def test_align_leaves_profile_on_persistent_homology() -> None:
    lcms = _lcms("profile")
    method = align_peak_picking_to_ms1_format(lcms)
    assert method == PROFILE_PEAK_PICKING
    assert lcms.parameters.lc_ms.peak_picking_method == PROFILE_PEAK_PICKING


def test_align_flips_profile_off_centroided_method() -> None:
    lcms = _lcms("profile")
    lcms.parameters.lc_ms.peak_picking_method = CENTROID_PEAK_PICKING
    method = align_peak_picking_to_ms1_format(lcms)
    assert method == PROFILE_PEAK_PICKING
    assert lcms.parameters.lc_ms.peak_picking_method == PROFILE_PEAK_PICKING
