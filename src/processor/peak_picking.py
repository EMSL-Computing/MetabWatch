"""Match CoreMS peak picking to MS1 profile vs centroided data."""

from __future__ import annotations

PROFILE_PEAK_PICKING = "persistent homology"
CENTROID_PEAK_PICKING = "centroided_persistent_homology"


def ms1_scan_format(lcms_obj) -> str:
    """Return ``profile`` or ``centroid`` when every MS1 scan uses that format.

    Raises
    ------
    ValueError
        If there are no MS1 scans, or MS1 mixes profile and centroid.
    """
    scan_df = getattr(lcms_obj, "scan_df", None)
    if scan_df is None or getattr(scan_df, "empty", True):
        raise ValueError("No scan metadata on LCMS object; cannot choose peak picking.")
    if "ms_level" not in scan_df.columns or "ms_format" not in scan_df.columns:
        raise ValueError("LCMS scan table is missing ms_level or ms_format.")
    ms1 = scan_df[scan_df["ms_level"] == 1]
    if ms1.empty:
        raise ValueError("No MS1 scans found; cannot choose peak picking method.")
    formats = {str(value).strip().lower() for value in ms1["ms_format"].tolist()}
    if formats == {"centroid"}:
        return "centroid"
    if formats == {"profile"}:
        return "profile"
    raise ValueError(
        "MS1 scans mix formats "
        + ", ".join(sorted(formats))
        + "; MetabWatch needs all MS1 scans to be profile or all centroid."
    )


def align_peak_picking_to_ms1_format(lcms_obj) -> str:
    """Flip CoreMS peak picking to match MS1 data, as MetaMS does.

    Centroided MS1 uses ``centroided_persistent_homology`` and relative-abundance
    MS1 noise thresholding. Profile MS1 uses ``persistent homology``. The
    packaged TOML is not rewritten.
    """
    fmt = ms1_scan_format(lcms_obj)
    current = str(lcms_obj.parameters.lc_ms.peak_picking_method)
    if fmt == "centroid" and current != CENTROID_PEAK_PICKING:
        lcms_obj.parameters.lc_ms.peak_picking_method = CENTROID_PEAK_PICKING
        ms1_params = getattr(lcms_obj.parameters, "mass_spectrum", {}).get("ms1")
        if ms1_params is not None:
            ms1_params.mass_spectrum.noise_threshold_method = "relative_abundance"
        print(
            "[peak-picking] MS1 is centroided; switching to "
            "centroided_persistent_homology"
        )
        return CENTROID_PEAK_PICKING
    if fmt == "profile" and current != PROFILE_PEAK_PICKING:
        lcms_obj.parameters.lc_ms.peak_picking_method = PROFILE_PEAK_PICKING
        print("[peak-picking] MS1 is profile; switching to persistent homology")
        return PROFILE_PEAK_PICKING
    return current
