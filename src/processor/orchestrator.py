from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from targeted_search_for_standards import process_raw_to_observed_features_df


@dataclass(frozen=True)
class RetryPolicy:
    """Retry/backoff policy for processing attempts.

    Parameters
    ----------
    max_retries : int
        Maximum number of retry attempts allowed.
    initial_backoff_sec : float
        Initial backoff delay in seconds.
    backoff_multiplier : float
        Multiplier applied to backoff after each retry.
    """

    max_retries: int
    initial_backoff_sec: float
    backoff_multiplier: float


@dataclass(frozen=True)
class ProcessResult:
    """Result summary returned by the processor orchestrator.

    Parameters
    ----------
    raw_file : Path
        Path to the processed `.raw` file.
    status : str
        One of 'completed' or 'failed'.
    output_csv : Path | None
        Path to the written matches CSV when completed.
    trace_csv : Path | None
        Path to the MS1 trace CSV when completed.
    rows : int
        Number of matched rows written.
    error : str | None
        Error message for failed runs.
    retryable : bool
        Whether the failure is considered retryable.
    acquisition_time : str | None
        Acquisition timestamp extracted from CoreMS metadata.
    polarity : str | None
        CoreMS ionization polarity when known (``positive`` / ``negative``).
    """

    raw_file: Path
    status: str
    output_csv: Path | None = None
    trace_csv: Path | None = None
    rows: int = 0
    error: str | None = None
    retryable: bool = False
    acquisition_time: str | None = None
    polarity: str | None = None


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
        integrate_mass_features: bool,
        cluster_mass_features: bool,
    ):
        self.standards_csv = standards_csv
        self.params_path = params_path
        self.output_dir = output_dir
        self.mz_tolerance_ppm = mz_tolerance_ppm
        self.rt_tolerance = rt_tolerance
        self.min_area = min_area
        self.plot_eics = plot_eics
        self.plot_tic = plot_tic
        self.integrate_mass_features = integrate_mass_features
        self.cluster_mass_features = cluster_mass_features
        """Wrap invocation of the CoreMS-based processing function.

        Parameters
        ----------
        standards_csv, params_path, output_dir, mz_tolerance_ppm, rt_tolerance,
        min_area, plot_eics, plot_tic
            See attribute names for meanings.
        """

    @staticmethod
    def _is_retryable(exc: Exception) -> bool:
        """Heuristic check whether an exception message indicates a transient error.

        Parameters
        ----------
        exc : Exception
            The exception raised during processing.

        Returns
        -------
        bool
            True if the message contains retry hints.
        """
        text = str(exc).lower()
        if "polarity mismatch" in text:
            return False
        retry_hints = ("temporar", "locked", "timeout", "i/o", "resource busy")
        return any(hint in text for hint in retry_hints)

    def process_single_raw(
        self,
        raw_file: Path,
        *,
        expected_polarity: str | None = None,
    ) -> ProcessResult:
        """Process a single raw file and return a ProcessResult.

        Parameters
        ----------
        raw_file : Path
            Path to the `.raw` file to process.
        expected_polarity : str | None
            When set (from the pipeline manifest), the sample must match.

        Returns
        -------
        ProcessResult
            Summary including artifact paths or error information.
        """
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
                integrate_mass_features=self.integrate_mass_features,
                cluster_mass_features=self.cluster_mass_features,
                expected_polarity=expected_polarity,
            )
            stem = raw_file.stem
            acquisition_time = results_df.attrs.get("acquisition_time")
            if "acquisition_time" in results_df.columns and not results_df.empty:
                acquisition_time = str(results_df["acquisition_time"].iloc[0])
            polarity = results_df.attrs.get("polarity")
            if polarity is not None:
                polarity = str(polarity).strip().lower()
            return ProcessResult(
                raw_file=raw_file,
                status="completed",
                output_csv=self.output_dir / f"{stem}_targeted_matches.csv",
                trace_csv=self.output_dir / f"{stem}_ms1_traces.csv",
                rows=len(results_df),
                retryable=False,
                acquisition_time=acquisition_time,
                polarity=polarity,
            )
        except Exception as exc:
            retryable = self._is_retryable(exc)
            return ProcessResult(
                raw_file=raw_file,
                status="failed",
                error=str(exc),
                retryable=retryable,
            )
