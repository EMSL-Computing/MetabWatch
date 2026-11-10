"""Thermo readers are closed when a sample finishes or fails."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest
from corems.encapsulation.factory.parameters import LCMSParameters

from metabwatch.pipeline_queue import close_thermo_reader
from metabwatch.processor.untargeted import build_untargeted_search_space
from metabwatch.targeted_search_for_standards import process_raw_to_observed_features_df

_PARAMS = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "presets"
    / "hilic_metab_pnnl"
    / "corems.toml"
)


class _CountingParser:
    def __init__(self, raw_file: Path) -> None:
        self.raw_file = raw_file
        self.close_calls = 0

    def close_file(self) -> None:
        self.close_calls += 1

    def get_creation_time(self) -> str:
        return "2026-01-01T00:00:00+00:00"


class _FakeFeature:
    def __init__(self, mz: float, scan_time: float, area: float) -> None:
        self.mz = mz
        self.scan_time = scan_time
        self.area = area
        self.isotopologue_type = None
        # Survive the packaged HILIC peak-metric keep-rules.
        self._gaussian_similarity = 0.91
        self.tailing_factor = 1.1
        self.noise_score_min = 0.6
        self.noise_score_max = 0.9


class _FakeLcms:
    """Minimal LCMS stand-in for the untargeted close tests."""

    def __init__(self) -> None:
        self.polarity = "positive"
        self.parameters = LCMSParameters(use_defaults=True)
        self.mass_features = {
            1: _FakeFeature(100.1, 1.2, 1.0e6),
            2: _FakeFeature(150.2, 2.3, 5.0e5),
        }
        self.scan_df = pd.DataFrame(
            {"ms_level": [1, 1], "ms_format": ["profile", "profile"]}
        )

    def find_mass_features(self) -> None:
        return None

    def integrate_mass_features(self, **kwargs) -> None:
        return None

    def cluster_mass_features(self, **kwargs) -> None:
        return None

    def add_peak_metrics(self, **kwargs) -> None:
        return None

    def find_c13_mass_features(self) -> None:
        return None

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


def test_close_thermo_reader_ignores_missing_and_failed_close() -> None:
    class _Boom:
        def close_file(self) -> None:
            raise RuntimeError("close failed")

    close_thermo_reader(None)
    close_thermo_reader(object())
    close_thermo_reader(_Boom())

    parser = _CountingParser(Path("sample.raw"))
    close_thermo_reader(parser)
    close_thermo_reader(parser)
    assert parser.close_calls == 2


def test_untargeted_closes_reader_after_success(tmp_path: Path, monkeypatch) -> None:
    raw = tmp_path / "Pool.raw"
    raw.write_bytes(b"x")
    out = tmp_path / "untargeted_search_space.csv"
    fake = _FakeLcms()
    holder: dict[str, _CountingParser] = {}

    class _Parser(_CountingParser):
        def get_lcms_obj(self, spectra: str = "ms1") -> _FakeLcms:
            return fake

    def _factory(raw_file: Path) -> _Parser:
        parser = _Parser(raw_file)
        holder["parser"] = parser
        return parser

    monkeypatch.setattr(
        "metabwatch.processor.untargeted.ImportMassSpectraThermoMSFileReader",
        _factory,
    )

    result = build_untargeted_search_space(
        raw_file=raw,
        params_path=_PARAMS,
        output_csv=out,
        top_n=10,
        mz_tolerance_ppm=5.0,
    )

    assert list(result["compound_name"]) == ["feature_001", "feature_002"]
    assert holder["parser"].close_calls == 1


def test_untargeted_closes_reader_when_peak_picking_fails(
    tmp_path: Path, monkeypatch
) -> None:
    raw = tmp_path / "Pool.raw"
    raw.write_bytes(b"x")
    out = tmp_path / "untargeted_search_space.csv"
    fake = _FakeLcms()

    def _fail() -> None:
        raise RuntimeError("peak pick failed")

    fake.find_mass_features = _fail  # type: ignore[method-assign]
    holder: dict[str, _CountingParser] = {}

    class _Parser(_CountingParser):
        def get_lcms_obj(self, spectra: str = "ms1") -> _FakeLcms:
            return fake

    def _factory(raw_file: Path) -> _Parser:
        parser = _Parser(raw_file)
        holder["parser"] = parser
        return parser

    monkeypatch.setattr(
        "metabwatch.processor.untargeted.ImportMassSpectraThermoMSFileReader",
        _factory,
    )

    with pytest.raises(RuntimeError, match="peak pick failed"):
        build_untargeted_search_space(
            raw_file=raw,
            params_path=_PARAMS,
            output_csv=out,
            top_n=10,
            mz_tolerance_ppm=5.0,
        )

    assert holder["parser"].close_calls == 1
    assert not out.exists()


def _standards_csv(path: Path) -> None:
    path.write_text(
        "compound_name,ion_type,mz,retention_time,polarity\n"
        "Glucose,[M+H]+,100.1,1.2,positive\n",
        encoding="utf-8",
    )


def test_targeted_closes_reader_when_parse_fails(tmp_path: Path, monkeypatch) -> None:
    raw = tmp_path / "QC.raw"
    raw.write_bytes(b"x")
    standards = tmp_path / "standards.csv"
    _standards_csv(standards)
    holder: dict[str, _CountingParser] = {}

    class _Parser(_CountingParser):
        def get_lcms_obj(self, spectra: str = "ms1"):
            raise RuntimeError("cannot read raw")

    def _factory(raw_file: Path) -> _Parser:
        parser = _Parser(raw_file)
        holder["parser"] = parser
        return parser

    monkeypatch.setattr(
        "metabwatch.targeted_search_for_standards.ImportMassSpectraThermoMSFileReader",
        _factory,
    )

    with pytest.raises(RuntimeError, match="Failed to parse raw file"):
        process_raw_to_observed_features_df(
            raw_file=raw,
            standards_csv=standards,
            params_path=_PARAMS,
            output_dir=tmp_path / "out",
            plot_eics=False,
            plot_tic=False,
        )

    assert holder["parser"].close_calls == 1


def test_targeted_closes_reader_when_peak_picking_fails(
    tmp_path: Path, monkeypatch
) -> None:
    raw = tmp_path / "QC.raw"
    raw.write_bytes(b"x")
    standards = tmp_path / "standards.csv"
    _standards_csv(standards)
    holder: dict[str, _CountingParser] = {}

    class _Parser(_CountingParser):
        def get_lcms_obj(self, spectra: str = "ms1"):
            lcms = SimpleNamespace(
                polarity="positive",
                parameters=LCMSParameters(use_defaults=True),
                scan_df=pd.DataFrame(
                    {"ms_level": [1], "ms_format": ["profile"]}
                ),
            )

            def find_mass_features(**kwargs) -> None:
                raise RuntimeError("peak pick failed")

            lcms.find_mass_features = find_mass_features
            return lcms

    def _factory(raw_file: Path) -> _Parser:
        parser = _Parser(raw_file)
        holder["parser"] = parser
        return parser

    monkeypatch.setattr(
        "metabwatch.targeted_search_for_standards.ImportMassSpectraThermoMSFileReader",
        _factory,
    )

    with pytest.raises(RuntimeError, match="peak pick failed"):
        process_raw_to_observed_features_df(
            raw_file=raw,
            standards_csv=standards,
            params_path=_PARAMS,
            output_dir=tmp_path / "out",
            plot_eics=False,
            plot_tic=False,
        )

    assert holder["parser"].close_calls == 1
