"""Tests for the GUI pipeline runner (mocked watch mode)."""

from __future__ import annotations

import threading
import time
from pathlib import Path
from unittest.mock import patch

from metabwatch.gui.runner import PipelineRunner
from metabwatch.gui.validation import GuiRunRequest
from metabwatch.presets import build_pipeline_config


def _preset_request(tmp_path: Path, *, once: bool = True) -> GuiRunRequest:
    raw = tmp_path / "raw"
    raw.mkdir(exist_ok=True)
    return GuiRunRequest(
        source="preset",
        method="hilic_metab_pnnl",
        search="targeted",
        input_folder=str(raw),
        output_folder=str(tmp_path / "out"),
        once=once,
        force_reprocess=False,
    )


def test_runner_calls_watch_mode_with_stop_event(tmp_path: Path) -> None:
    runner = PipelineRunner()
    req = _preset_request(tmp_path)
    done = threading.Event()
    seen: dict = {}

    def fake_watch(*, config, once, force_reprocess, stop_event):
        seen["once"] = once
        seen["force"] = force_reprocess
        seen["stop_event"] = stop_event
        seen["output"] = config.processor.output_dir
        return 0

    def on_finished(state):
        seen["exit_code"] = state.exit_code
        done.set()

    with patch("metabwatch.gui.runner.run_watch_mode", side_effect=fake_watch):
        runner.start(req, on_finished=on_finished)
        assert done.wait(timeout=5.0)

    assert seen["once"] is True
    assert seen["force"] is False
    assert isinstance(seen["stop_event"], threading.Event)
    assert seen["exit_code"] == 0
    assert runner.output_dir() == (tmp_path / "out").resolve()
    assert runner.dashboard_path() is not None


def test_runner_request_stop_sets_event(tmp_path: Path) -> None:
    runner = PipelineRunner()
    req = _preset_request(tmp_path, once=False)
    entered = threading.Event()
    finished = threading.Event()

    def fake_watch(*, config, once, force_reprocess, stop_event):
        entered.set()
        # Simulate cooperative stop: wait until stop_event is set
        while not stop_event.is_set():
            time.sleep(0.02)
        return 0

    def on_finished(_state):
        finished.set()

    with patch("metabwatch.gui.runner.run_watch_mode", side_effect=fake_watch):
        runner.start(req, on_finished=on_finished)
        assert entered.wait(timeout=5.0)
        assert runner.is_running
        runner.request_stop()
        assert finished.wait(timeout=5.0)

    assert not runner.is_running


def test_runner_rejects_double_start(tmp_path: Path) -> None:
    import pytest

    runner = PipelineRunner()
    req = _preset_request(tmp_path, once=False)
    block = threading.Event()
    started = threading.Event()

    def fake_watch(*, config, once, force_reprocess, stop_event):
        started.set()
        block.wait(timeout=5.0)
        return 0

    with patch("metabwatch.gui.runner.run_watch_mode", side_effect=fake_watch):
        runner.start(req)
        assert started.wait(timeout=5.0)
        try:
            with pytest.raises(RuntimeError, match="already in progress"):
                runner.start(req)
        finally:
            block.set()
            for _ in range(50):
                if not runner.is_running:
                    break
                time.sleep(0.05)


def test_resolve_matches_preset_api(tmp_path: Path) -> None:
    """Sanity: runner's config path matches direct build_pipeline_config."""
    raw = tmp_path / "raw"
    raw.mkdir()
    out = tmp_path / "out"
    direct = build_pipeline_config("hilic_metab_pnnl", "targeted", raw, out)
    from metabwatch.gui.validation import resolve_config

    via_gui = resolve_config(
        GuiRunRequest(
            source="preset",
            method="hilic_metab_pnnl",
            search="targeted",
            input_folder=str(raw),
            output_folder=str(out),
        )
    )
    assert via_gui.processor.params_path == direct.processor.params_path
    assert via_gui.watcher.sample_name_regex == direct.watcher.sample_name_regex
