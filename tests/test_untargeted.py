"""Untargeted bootstrap calls CoreMS peak-metric filtering; targeted does not."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from corems.encapsulation.factory.parameters import LCMSParameters
from metabwatch.processor.untargeted import build_untargeted_search_space


class _FakeLcms:
    def __init__(self) -> None:
        self.polarity = "positive"
        self.parameters = LCMSParameters(use_defaults=True)
        self.calls: list[str] = []

    def find_mass_features(self) -> None:
        self.calls.append("find")

    def integrate_mass_features(self, **kwargs) -> None:
        self.calls.append("integrate")

    def cluster_mass_features(self, **kwargs) -> None:
        self.calls.append("cluster")

    def add_peak_metrics(self, **kwargs) -> None:
        self.calls.append("metrics")

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

    assert fake.calls == ["find", "integrate", "cluster", "integrate", "metrics"]
    assert fake.parameters.lc_ms.remove_mass_features_by_peak_metrics is True
    assert out.is_file()
    assert list(result["compound_name"]) == ["feature_001"]
