"""Unit tests for mass-feature and target EIC lookup used in trace CSV export."""

from __future__ import annotations

from types import SimpleNamespace

from metabwatch.targeted_search_for_standards import (
    _eic_data_for_mass_feature,
    _eic_data_for_mz,
)


class _Eic:
    def __init__(self, label: str) -> None:
        self.label = label
        self.scans = [1, 2]
        self.eic = [10.0, 20.0]


class _MassFeature:
    def __init__(self, mz: float, eic_data: _Eic | None = None) -> None:
        self.mz = mz
        self._eic_data = eic_data


class _Lcms:
    def __init__(
        self,
        *,
        eics: dict[float, _Eic] | None,
        mass_features: dict[int, _MassFeature],
        exact_key: float | None = None,
        raise_on_lookup: bool = False,
    ) -> None:
        self.eics = eics
        self.mass_features = mass_features
        self._exact_key = exact_key
        self._raise_on_lookup = raise_on_lookup

    def get_eic_mz_for_mass_feature(self, mz: float, tolerance: float | None = None):
        if self._raise_on_lookup:
            raise RuntimeError("no EIC key")
        return self._exact_key


def test_mass_feature_prefers_attached_eic_data() -> None:
    attached = _Eic("attached")
    lcms = _Lcms(
        eics={100.0: _Eic("from_eics")},
        mass_features={3: _MassFeature(mz=100.0, eic_data=attached)},
        exact_key=100.0,
    )
    found = _eic_data_for_mass_feature(lcms, 3, mz_tolerance_ppm=5.0)
    assert found is attached


def test_mass_feature_uses_exact_eics_key_when_attached_missing() -> None:
    exact = _Eic("exact")
    lcms = _Lcms(
        eics={100.012: exact},
        mass_features={3: _MassFeature(mz=100.012, eic_data=None)},
        exact_key=100.012,
    )
    found = _eic_data_for_mass_feature(lcms, 3, mz_tolerance_ppm=5.0)
    assert found is exact


def test_mass_feature_falls_back_to_nearest_eic_key() -> None:
    nearest = _Eic("nearest")
    lcms = _Lcms(
        eics={100.2: nearest, 110.0: _Eic("far")},
        mass_features={3: _MassFeature(mz=100.0, eic_data=None)},
        exact_key=None,
    )
    found = _eic_data_for_mass_feature(lcms, 3, mz_tolerance_ppm=5.0)
    assert found is nearest


def test_mass_feature_returns_none_when_no_eics() -> None:
    lcms = _Lcms(
        eics=None,
        mass_features={3: _MassFeature(mz=100.0, eic_data=None)},
        exact_key=None,
    )
    assert _eic_data_for_mass_feature(lcms, 3, mz_tolerance_ppm=5.0) is None


def test_target_mz_falls_back_to_nearest_when_lookup_raises() -> None:
    nearest = _Eic("nearest")
    lcms = _Lcms(
        eics={195.1: nearest},
        mass_features={},
        exact_key=None,
        raise_on_lookup=True,
    )
    found = _eic_data_for_mz(lcms, 195.0, mz_tolerance_ppm=5.0)
    assert found is nearest


def test_mz_lookup_without_get_eic_method() -> None:
    """Duck-typed LCMS objects without get_eic_mz_for_mass_feature still resolve."""
    nearest = _Eic("nearest")
    lcms = SimpleNamespace(
        eics={50.0: nearest},
        mass_features={1: _MassFeature(mz=49.9, eic_data=None)},
    )
    found = _eic_data_for_mz(lcms, 49.9, mz_tolerance_ppm=5.0)
    assert found is nearest
