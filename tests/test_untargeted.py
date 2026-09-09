"""Untargeted bootstrap calls CoreMS peak-metric filtering; targeted does not."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from types import SimpleNamespace

from corems.encapsulation.factory.parameters import LCMSParameters
from metabwatch.processor.untargeted import (
    _apply_peak_metric_filters,
    _peak_metric_value,
    build_untargeted_search_space,
)


class _FakeLcms:
    def __init__(self) -> None:
        self.polarity = "positive"
        self.parameters = LCMSParameters(use_defaults=True)
        self.mass_features: dict = {}
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

    def mass_features_to_df(self, drop_na_cols: bool = True) -> pd.DataFrame:
        return pd.DataFrame(
            {"mz": [100.1], "scan_time": [1.2], "area": [1.0e6]}
        )


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
    ]
    assert fake.parameters.lc_ms.remove_mass_features_by_peak_metrics is True
    assert fake.parameters.lc_ms.mass_feature_attribute_filter_dict[
        "gaussian_similarity"
    ]["value"] == 0.7
    assert fake.parameters.lc_ms.mass_feature_attribute_filter_dict[
        "tailing_factor"
    ]["value"] == 1.5
    assert out.is_file()
    assert list(result["compound_name"]) == ["feature_001"]


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
