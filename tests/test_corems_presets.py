"""Packaged CoreMS TOMLs are LC-MS overrides vs CoreMS 4.0.1 defaults."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from corems.encapsulation.factory.parameters import LCMSParameters
from corems.encapsulation.factory.processingSetting import LiquidChromatographSetting
from corems.encapsulation.input.parameter_from_json import (
    _set_dict_data_lcms,
    load_and_set_toml_parameters_lcms,
)

try:
    import tomllib
except ImportError:  # pragma: no cover
    import tomli as tomllib

_PRESETS = Path(__file__).resolve().parents[1] / "src" / "presets"

# Keys MetabWatch actually uses that differ from CoreMS 4.0.1 defaults.
_SHARED_LC_KEYS = {
    "smooth_window",
    "consecutive_scan_min",
    "min_peak_datapoints",
    "ph_smooth_it",
    "ph_inten_min_rel",
    "ph_persis_min_rel",
    "mass_feature_cluster_rt_tolerance",
    "remove_mass_features_by_peak_metrics",
    "verbose_processing",
}
_HILIC_PNNL_KEYS = _SHARED_LC_KEYS | {"remove_redundant_mass_features"}
_HILIC_OLYMPIC_KEYS = set(_SHARED_LC_KEYS)
_RP_KEYS = _SHARED_LC_KEYS | {
    "mass_feature_cluster_mz_tolerance_rel",
    "remove_redundant_mass_features",
}

_EXPECTED_KEYS = {
    "hilic_metab_pnnl": _HILIC_PNNL_KEYS,
    "hilic_metab_olympic_eclipse01": _HILIC_OLYMPIC_KEYS,
    "rp_metab_pnnl": _RP_KEYS,
    "rp_metab_olympic_eclipse01": _RP_KEYS,
}


def _toml_path(method: str) -> Path:
    return _PRESETS / method / "corems.toml"


def _load_toml(method: str) -> dict:
    return tomllib.loads(_toml_path(method).read_text(encoding="utf-8"))


def _apply(method: str) -> SimpleNamespace:
    obj = SimpleNamespace(parameters=LCMSParameters(use_defaults=True))
    load_and_set_toml_parameters_lcms(obj, _toml_path(method))
    return obj


@pytest.mark.parametrize("method", sorted(_EXPECTED_KEYS))
def test_preset_toml_is_lc_overrides_only(method: str) -> None:
    data = _load_toml(method)
    assert set(data) == {"LiquidChromatograph", "mass_spectrum"}
    assert data["mass_spectrum"] == {}
    assert set(data["LiquidChromatograph"]) == _EXPECTED_KEYS[method]


@pytest.mark.parametrize("method", sorted(_EXPECTED_KEYS))
def test_preset_toml_loads_on_corems_defaults(method: str) -> None:
    lc = _apply(method).parameters.lc_ms
    default = LiquidChromatographSetting()

    assert lc.smooth_window == 9
    assert lc.consecutive_scan_min == 5
    assert lc.min_peak_datapoints == 2.0
    assert lc.ph_smooth_it == 0
    assert lc.ph_inten_min_rel == 0.003
    assert lc.ph_persis_min_rel == 0.003
    assert lc.mass_feature_cluster_rt_tolerance == 0.1
    assert lc.remove_mass_features_by_peak_metrics is True
    assert lc.verbose_processing is False
    # Unset LC keys keep CoreMS defaults used by this pipeline.
    assert lc.peak_picking_method == default.peak_picking_method
    assert lc.eic_tolerance_ppm == default.eic_tolerance_ppm
    assert lc.smooth_method == default.smooth_method


def test_hilic_pnnl_enables_redundant_feature_removal() -> None:
    lc = _apply("hilic_metab_pnnl").parameters.lc_ms
    assert lc.remove_redundant_mass_features is True
    assert lc.mass_feature_cluster_mz_tolerance_rel == 5e-6


def test_hilic_olympic_keeps_corems_redundant_feature_default() -> None:
    lc = _apply("hilic_metab_olympic_eclipse01").parameters.lc_ms
    assert lc.remove_redundant_mass_features is False
    assert lc.mass_feature_cluster_mz_tolerance_rel == 5e-6


@pytest.mark.parametrize(
    "method",
    ["rp_metab_pnnl", "rp_metab_olympic_eclipse01"],
)
def test_rp_tightens_cluster_mz(method: str) -> None:
    lc = _apply(method).parameters.lc_ms
    assert lc.mass_feature_cluster_mz_tolerance_rel == 3e-6
    assert lc.remove_redundant_mass_features is True


@pytest.mark.parametrize("method", sorted(_EXPECTED_KEYS))
def test_preset_toml_does_not_replace_ms1_defaults(method: str) -> None:
    applied = _apply(method).parameters.mass_spectrum["ms1"]
    fresh = LCMSParameters(use_defaults=True).mass_spectrum["ms1"]
    assert applied.mass_spectrum.noise_min_mz == fresh.mass_spectrum.noise_min_mz
    assert applied.mass_spectrum.min_picking_mz == fresh.mass_spectrum.min_picking_mz
    assert applied.molecular_search.url_database == fresh.molecular_search.url_database
    assert "ms2_cid" not in _apply(method).parameters.mass_spectrum


def test_corems_4_0_1_loader_requires_mass_spectrum_table() -> None:
    obj = SimpleNamespace(parameters=LCMSParameters(use_defaults=True))
    with pytest.raises(KeyError):
        _set_dict_data_lcms({"LiquidChromatograph": {"smooth_window": 9}}, obj)
