"""Unit tests for sample_name_regex AND optional project_id gating."""

from __future__ import annotations

from pathlib import Path

from metabwatch.pipeline import _compile_sample_regex, _sample_allowed, _sample_ignore_reason
from metabwatch.presets import build_pipeline_config


POOL = _compile_sample_regex(r"(?i)Pool")
QC = _compile_sample_regex(r"QC_Metab_(.+)")


def test_empty_project_id_does_not_change_regex() -> None:
    assert _sample_allowed(Path("PoolQC_01.raw"), POOL, "")
    assert _sample_allowed(Path("Pooled_QC.raw"), POOL, "")
    assert not _sample_allowed(Path("QC_Metab_25-02_x.raw"), POOL, "")
    assert _sample_allowed(Path("QC_Metab_25-02_x.raw"), QC, "")
    assert not _sample_allowed(Path("PoolQC_01.raw"), QC, "")


def test_project_id_and_pool_regex() -> None:
    """Untargeted Pool regex still applies when a project_id is set."""
    keep = Path("Pool_25-02_HILIC_Pos.raw")
    other_batch = Path("Pool_24-11_HILIC_Pos.raw")
    qc_same_batch = Path("QC_Metab_25-02_HILIC_Pos.raw")

    assert _sample_allowed(keep, POOL, "25-02")
    assert not _sample_allowed(other_batch, POOL, "25-02")
    assert _sample_ignore_reason(other_batch, POOL, "25-02") == "project_id no match"
    # Same project id but missing Pool — still rejected by the regex.
    assert not _sample_allowed(qc_same_batch, POOL, "25-02")
    assert _sample_ignore_reason(qc_same_batch, POOL, "25-02") == "sample_name_regex no match"


def test_project_id_case_insensitive() -> None:
    assert _sample_allowed(Path("Pool_BatchA_01.raw"), POOL, "batcha")


def test_preset_untargeted_keeps_pool_with_project_id(tmp_path: Path) -> None:
    cfg = build_pipeline_config(
        "hilic_metab_pnnl",
        "untargeted",
        tmp_path,
        tmp_path,
        project_id="25-02",
    )
    regex = _compile_sample_regex(cfg.watcher.sample_name_regex)
    assert regex is not None
    assert _sample_allowed(Path("pool_25-02_x.raw"), regex, cfg.watcher.project_id)
    assert not _sample_allowed(Path("QC_Metab_25-02_x.raw"), regex, cfg.watcher.project_id)
