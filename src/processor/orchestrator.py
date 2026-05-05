from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from targeted_search_for_standards import process_raw_to_observed_features_df


@dataclass(frozen=True)
class RetryPolicy:
    max_retries: int
    initial_backoff_sec: float
    backoff_multiplier: float


@dataclass(frozen=True)
class ProcessResult:
    raw_file: Path
    status: str
    output_csv: Path | None = None
    trace_csv: Path | None = None
    rows: int = 0
    error: str | None = None
    retryable: bool = False


class ProcessorOrchestrator:
    def __init__(
        self,
        standards_csv: Path,
        params_path: Path,
        output_dir: Path,
        mz_tolerance_ppm: float,
        rt_tolerance: float,
        min_area: float,
        plot_eics: bool,
        plot_tic: bool,
    ):
        self.standards_csv = standards_csv
        self.params_path = params_path
        self.output_dir = output_dir
        self.mz_tolerance_ppm = mz_tolerance_ppm
        self.rt_tolerance = rt_tolerance
        self.min_area = min_area
        self.plot_eics = plot_eics
        self.plot_tic = plot_tic

    @staticmethod
    def _is_retryable(exc: Exception) -> bool:
        text = str(exc).lower()
        retry_hints = ("temporar", "locked", "timeout", "i/o", "resource busy")
        return any(hint in text for hint in retry_hints)

    def process_single_raw(self, raw_file: Path) -> ProcessResult:
        try:
            results_df = process_raw_to_observed_features_df(
                raw_file=raw_file,
                standards_csv=self.standards_csv,
                params_path=self.params_path,
                output_dir=self.output_dir,
                mz_tolerance_ppm=self.mz_tolerance_ppm,
                rt_tolerance=self.rt_tolerance,
                min_area=self.min_area,
                plot_eics=self.plot_eics,
                plot_tic=self.plot_tic,
            )
            stem = raw_file.stem
            return ProcessResult(
                raw_file=raw_file,
                status="completed",
                output_csv=self.output_dir / f"{stem}_targeted_matches.csv",
                trace_csv=self.output_dir / f"{stem}_ms1_traces.csv",
                rows=len(results_df),
                retryable=False,
            )
        except Exception as exc:
            retryable = self._is_retryable(exc)
            return ProcessResult(
                raw_file=raw_file,
                status="failed",
                error=str(exc),
                retryable=retryable,
            )
