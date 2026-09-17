"""Untargeted bootstrap calls CoreMS peak-metric filtering; targeted does not."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from types import SimpleNamespace

from corems.encapsulation.factory.parameters import LCMSParameters
from metabwatch.processor.untargeted import (
    _apply_peak_metric_filters,
    _drop_c13_isotopologues,
    _isotopologue_type,
    _peak_metric_value,
    build_untargeted_search_space,
)


class _FakeFeature:
    def __init__(
        self,
        mz: float,
        scan_time: float,
        area: float,
        *,
        isotopologue_type: str | None = None,
        mark_as_c13: bool = False,
    ) -> None:
        self.mz = mz
        self.scan_time = scan_time
        self.retention_time = scan_time
        self.area = area
        self.isotopologue_type = isotopologue_type
        self.mark_as_c13 = mark_as_c13
        # Survive packaged peak-metric keep-rules when used in the full bootstrap.
        self._gaussian_similarity = 0.91
        self.tailing_factor = 1.1
        self.noise_score_min = 0.6
        self.noise_score_max = 0.9


class _FakeLcms:
    def __init__(self, mass_features: dict | None = None) -> None:
        self.polarity = "positive"
        self.parameters = LCMSParameters(use_defaults=True)
        self.mass_features: dict = mass_features or {
            1: _FakeFeature(100.1, 1.2, 1.0e6),
            2: _FakeFeature(150.2, 2.3, 5.0e5),
        }
        self.scan_df = pd.DataFrame(
            {"ms_level": [1, 1], "ms_format": ["profile", "profile"]}
        )
        self.calls: list[str] = []

    def find_mass_features(self) -> None:
        self.calls.append("find")

    def integrate_mass_features(self, **kwargs) -> None:
        self.calls.append("integrate")

    def cluster_mass_features(self, **kwargs) -> None:
        self.calls.append("cluster")

    def add_peak_metrics(self, **kwargs) -> None:
        self.calls.append(("metrics", kwargs))

    def find_c13_mass_features(self) -> None:
        self.calls.append("c13")
        for mass_feature in self.mass_features.values():
            if getattr(mass_feature, "mark_as_c13", False):
                mass_feature.isotopologue_type = "13C1"

    def mass_features_to_df(self, drop_na_cols: bool = True) -> pd.DataFrame:
        rows = [
            {
                "mz": mass_feature.mz,
                "scan_time": mass_feature.scan_time,
                "area": mass_feature.area,
            }
            for mass_feature in self.mass_features.values()
        ]
        return pd.DataFrame(rows)


def test_untargeted_calls_add_peak_metrics_after_integrate(
    tmp_path: Path, monkeypatch
) -> None:
    raw = tmp_path / "Pool.raw"
    raw.write_bytes(b"x")
    params = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "presets"
        / "rp_metab_pnnl"
        / "corems.toml"
    )
    out = tmp_path / "untargeted_search_space.csv"
    fake = _FakeLcms()

    class _FakeParser:
        def __init__(self, raw_file: Path) -> None:
            self.raw_file = raw_file

        def get_lcms_obj(self, spectra: str = "ms1") -> _FakeLcms:
            return fake

    monkeypatch.setattr(
        "metabwatch.processor.untargeted.ImportMassSpectraThermoMSFileReader",
        _FakeParser,
    )

    result = build_untargeted_search_space(
        raw_file=raw,
        params_path=params,
        output_csv=out,
        top_n=10,
        mz_tolerance_ppm=5.0,
    )

    assert fake.calls == [
        "find",
        "integrate",
        "cluster",
        "integrate",
        ("metrics", {"remove_by_metrics": False}),
        "c13",
    ]
    assert fake.parameters.lc_ms.remove_mass_features_by_peak_metrics is True
    assert fake.parameters.lc_ms.mass_feature_attribute_filter_dict[
        "gaussian_similarity"
    ]["value"] == 0.7
    assert fake.parameters.lc_ms.mass_feature_attribute_filter_dict[
        "tailing_factor"
    ]["value"] == 1.5
    assert out.is_file()
    assert list(result["compound_name"]) == ["feature_001", "feature_002"]


def test_peak_metric_value_reads_corems_private_gaussian() -> None:
    feature = SimpleNamespace(_gaussian_similarity=0.91)
    assert _peak_metric_value(feature, "gaussian_similarity") == 0.91
    assert _peak_metric_value(feature, "tailing_factor") is None


def test_apply_peak_metric_filters_keeps_passing_private_gaussian() -> None:
    passing = SimpleNamespace(
        _gaussian_similarity=0.91,
        noise_score_min=0.6,
        noise_score_max=0.9,
        tailing_factor=1.1,
    )
    failing = SimpleNamespace(
        _gaussian_similarity=0.2,
        noise_score_min=0.6,
        noise_score_max=0.9,
        tailing_factor=1.1,
    )
    lcms = SimpleNamespace(
        parameters=SimpleNamespace(
            lc_ms=SimpleNamespace(
                mass_feature_attribute_filter_dict={
                    "gaussian_similarity": {"value": 0.7, "operator": ">="},
                    "tailing_factor": {"value": 1.5, "operator": "<="},
                    "noise_score_min": {"value": 0.5, "operator": ">="},
                    "noise_score_max": {"value": 0.8, "operator": ">="},
                }
            )
        ),
        mass_features={1: passing, 2: failing},
    )
    _apply_peak_metric_filters(lcms)
    assert set(lcms.mass_features) == {1}


def test_isotopologue_type_treats_blank_as_unmarked() -> None:
    assert _isotopologue_type(SimpleNamespace()) is None
    assert _isotopologue_type(SimpleNamespace(isotopologue_type=None)) is None
    assert _isotopologue_type(SimpleNamespace(isotopologue_type="")) is None
    assert _isotopologue_type(SimpleNamespace(isotopologue_type="  ")) is None
    assert _isotopologue_type(SimpleNamespace(isotopologue_type="13C1")) == "13C1"


def test_drop_c13_isotopologues_keeps_mono_and_unmarked() -> None:
    mono = _FakeFeature(100.0, 1.0, 2.0e6)
    satellite = _FakeFeature(101.0034, 1.0, 8.0e5, mark_as_c13=True)
    other = _FakeFeature(200.0, 2.0, 1.0e6)
    lcms = _FakeLcms(mass_features={1: mono, 2: satellite, 3: other})

    _drop_c13_isotopologues(lcms)

    assert lcms.calls == ["c13"]
    assert set(lcms.mass_features) == {1, 3}
    assert satellite.isotopologue_type == "13C1"


def test_drop_c13_isotopologues_skips_when_fewer_than_two_features() -> None:
    lcms = _FakeLcms(mass_features={1: _FakeFeature(100.0, 1.0, 1.0e6)})
    _drop_c13_isotopologues(lcms)
    assert lcms.calls == []
    assert set(lcms.mass_features) == {1}


def test_untargeted_top_n_is_applied_after_dropping_c13(
    tmp_path: Path, monkeypatch
) -> None:
    raw = tmp_path / "Pool.raw"
    raw.write_bytes(b"x")
    params = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "presets"
        / "rp_metab_pnnl"
        / "corems.toml"
    )
    out = tmp_path / "untargeted_search_space.csv"
    # Largest peak is a 13C satellite; after the drop, top_n=2 keeps the two
    # remaining (unmarked) features, not the satellite plus one other.
    fake = _FakeLcms(
        mass_features={
            1: _FakeFeature(100.0, 1.0, 5.0e5),
            2: _FakeFeature(200.0, 2.0, 4.0e5),
            3: _FakeFeature(101.0034, 1.0, 9.0e6, mark_as_c13=True),
        }
    )

    class _FakeParser:
        def __init__(self, raw_file: Path) -> None:
            self.raw_file = raw_file

        def get_lcms_obj(self, spectra: str = "ms1") -> _FakeLcms:
            return fake

    monkeypatch.setattr(
        "metabwatch.processor.untargeted.ImportMassSpectraThermoMSFileReader",
        _FakeParser,
    )

    result = build_untargeted_search_space(
        raw_file=raw,
        params_path=params,
        output_csv=out,
        top_n=2,
        mz_tolerance_ppm=5.0,
    )

    assert "c13" in fake.calls
    assert set(fake.mass_features) == {1, 2}
    assert list(result["mz"]) == [100.0, 200.0]
    assert list(result["compound_name"]) == ["feature_001", "feature_002"]
    written = pd.read_csv(out)
    assert list(written["mz"]) == [100.0, 200.0]
