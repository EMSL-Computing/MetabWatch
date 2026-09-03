from __future__ import annotations

import json
import re
import shutil
from datetime import datetime, timezone
from html import escape
from pathlib import Path

import pandas as pd

# Vendored Plotly.js (offline dashboards). Copied next to dashboard.html on render.
PLOTLY_JS_FILENAME = "plotly-2.35.2.min.js"
_PLOTLY_PACKAGE_PATH = Path(__file__).resolve().parent / "static" / PLOTLY_JS_FILENAME


class HTMLSynthesizer:
    """Generate a compound index and one dashboard page per detected compound.

    Parameters
    ----------
    output_dirs : tuple[Path, ...]
        Directories to search for per-sample output CSV files.
    html_output : Path
        Landing index path (`dashboard.html`).
    """

    def __init__(
        self,
        output_dirs: tuple[Path, ...],
        html_output: Path,
        mz_tolerance_ppm: float,
        rt_tolerance: float,
        untargeted_mode: bool = False,
    ):
        self.output_dirs = output_dirs
        self.html_output = html_output
        self.mz_tolerance_ppm = mz_tolerance_ppm
        self.rt_tolerance = rt_tolerance
        self.untargeted_mode = untargeted_mode
        self.last_compound_pages: int = 0
        self.last_skipped_samples: int = 0
        self.last_export_paths: dict[str, Path] = {}
        self.last_polarity_label: str = "unknown"

    @staticmethod
    def _slugify(name: str) -> str:
        slug = re.sub(r"[^0-9A-Za-z]+", "-", name).strip("-").lower()
        return slug or "compound"

    @staticmethod
    def format_run_polarity_label(polarities: set[str] | list[str]) -> str:
        """Format polarities collected from match CSVs for dashboard display.

        Parameters
        ----------
        polarities : set[str] | list[str]
            Normalized polarity strings (e.g. ``positive``, ``negative``).

        Returns
        -------
        str
            Single polarity, ``unknown``, or ``mixed (...)`` when more than one.
        """
        cleaned = sorted(
            {
                str(p).strip().lower()
                for p in polarities
                if p is not None and str(p).strip()
            }
        )
        if not cleaned:
            return "unknown"
        if len(cleaned) == 1:
            return cleaned[0]
        return f"mixed ({', '.join(cleaned)})"

    @staticmethod
    def _polarity_meta_html(polarity_label: str) -> str:
        """Return HTML for the polarity metadata line on dashboard pages."""
        is_mixed = polarity_label.startswith("mixed")
        style = (
            " style=\"color:#b42318;font-weight:700;\"" if is_mixed else ""
        )
        note = (
            " <span style=\"color:#b42318;\">(mixed polarities are not supported)</span>"
            if is_mixed
            else ""
        )
        return (
            f"<p class=\"meta-polarity\"{style}>"
            f"<strong>Polarity:</strong> {escape(polarity_label)}{note}</p>"
        )

    @staticmethod
    def _safe_trace_col(mf_id: int, compound_name: str) -> str:
        safe_name = re.sub(r"[^0-9A-Za-z]+", "_", compound_name).strip("_")
        return f"mf_{mf_id}_{safe_name}" if safe_name else f"mf_{mf_id}"

    @staticmethod
    def _target_trace_col(compound_name: str) -> str:
        safe_name = re.sub(r"[^0-9A-Za-z]+", "_", compound_name).strip("_")
        return f"target_{safe_name}" if safe_name else "target_compound"

    @staticmethod
    def _acquisition_label(acquisition_time_iso: str) -> str:
        """Return a readable UTC datetime label for x-axis ticks."""
        dt = pd.to_datetime(acquisition_time_iso, utc=True, errors="coerce")
        if pd.isna(dt):
            return acquisition_time_iso
        return dt.strftime("%Y-%m-%d %H:%M UTC")

    @staticmethod
    def _write_atomic(path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        tmp_path.write_text(content, encoding="utf-8")
        tmp_path.replace(path)

    def _ensure_plotly_asset(self) -> Path:
        """Copy vendored Plotly.js into the dashboard output directory.

        Returns
        -------
        Path
            Destination path next to ``dashboard.html`` (same folder).
        """
        if not _PLOTLY_PACKAGE_PATH.is_file():
            raise FileNotFoundError(
                f"Vendored Plotly.js missing: {_PLOTLY_PACKAGE_PATH}. "
                "Reinstall metabwatch or restore src/synthesis/static/."
            )
        dest = self.html_output.parent / PLOTLY_JS_FILENAME
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(_PLOTLY_PACKAGE_PATH, dest)
        return dest

    def write_placeholder_if_missing(self) -> Path:
        """Write a waiting-page dashboard when no dashboard HTML exists yet.

        Used at pipeline start so Open dashboard works while the first sample
        is still processing. Does not overwrite an existing dashboard
        (placeholder or full results).

        Returns
        -------
        Path
            Path to ``dashboard.html`` (existing or newly written).
        """
        if self.html_output.is_file():
            return self.html_output
        self._write_atomic(self.html_output, self._placeholder_html())
        return self.html_output

    @staticmethod
    def _placeholder_html() -> str:
        """Return HTML shown before the first synthesis completes."""
        return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <meta http-equiv="refresh" content="15" />
  <title>MetabWatch Compound Index</title>
  <style>
    :root {
      --bg: #f6f7f2;
      --panel: #ffffff;
      --ink: #1f2623;
      --line: #dde3dc;
      --accent: #24584b;
      --muted: #47524d;
    }
    body {
      margin: 0;
      padding: 24px;
      background: radial-gradient(circle at top right, #e4f1eb, var(--bg));
      color: var(--ink);
      font-family: "Avenir Next", "Segoe UI", sans-serif;
    }
    .card {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 14px;
      padding: 28px 24px;
      box-shadow: 0 8px 22px rgba(17, 24, 39, 0.08);
      max-width: 640px;
      margin: 48px auto;
    }
    h1 { margin: 0 0 12px; font-size: 1.5rem; }
    p { margin: 0 0 10px; color: var(--muted); line-height: 1.5; }
    .status {
      margin-top: 18px;
      padding: 14px 16px;
      border-radius: 10px;
      background: #eef6f2;
      border: 1px solid #c5ddd3;
      color: var(--accent);
      font-weight: 600;
    }
    .hint { margin-top: 16px; font-size: 0.95rem; }
  </style>
</head>
<body>
  <section class="card">
    <h1>MetabWatch Compound Index</h1>
    <p class="status">Processing first sample&hellip;</p>
    <p class="hint">Refresh this page to update once processing finishes (this page also auto-refreshes every 15 seconds).</p>
  </section>
</body>
</html>
"""

    @staticmethod
    def _write_atomic_csv(path: Path, df: pd.DataFrame) -> None:
        """Write a DataFrame to CSV via a temporary file for atomic replace."""
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        df.to_csv(tmp_path, index=False)
        tmp_path.replace(path)

    def _collect_match_csvs(self) -> list[Path]:
        paths: list[Path] = []
        for output_dir in self.output_dirs:
            if not output_dir.exists():
                continue
            paths.extend(sorted(output_dir.glob("*_targeted_matches.csv")))
        return sorted(set(paths))

    def _collect_manifest_acquisition_times(self) -> dict[str, str]:
        """Collect acquisition times keyed by output CSV absolute path."""
        mapping: dict[str, str] = {}
        for output_dir in self.output_dirs:
            manifest_path = output_dir / "pipeline_manifest.json"
            if not manifest_path.exists():
                continue
            try:
                payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            except Exception:
                continue
            for entry in payload.get("entries", []):
                out_csv = entry.get("output_csv")
                acq = entry.get("acquisition_time")
                if out_csv and acq:
                    mapping[str(Path(out_csv).resolve())] = str(acq)
        return mapping

    def _build_dataset(self) -> tuple[list[dict], dict[str, dict], set[str]]:
        """Build sample and compound records from matches and traces CSV files.

        Returns
        -------
        samples, compounds, polarities
            Sample records, compound index, and the set of normalized polarity
            values seen across match CSVs (for dashboard labeling).
        """
        manifest_times = self._collect_manifest_acquisition_times()
        samples: list[dict] = []
        compounds: dict[str, dict] = {}
        polarities: set[str] = set()
        self.last_skipped_samples = 0

        for match_csv in self._collect_match_csvs():
            try:
                df = pd.read_csv(match_csv)
            except Exception:
                continue

            sample_name = match_csv.name.replace("_targeted_matches.csv", "")
            trace_csv = match_csv.with_name(f"{sample_name}_ms1_traces.csv")
            if not trace_csv.exists():
                continue

            if "polarity" in df.columns and not df.empty:
                for value in df["polarity"].dropna().astype(str):
                    normalized = value.strip().lower()
                    if normalized:
                        polarities.add(normalized)

            acq_value = None
            if "acquisition_time" in df.columns and not df.empty:
                acq_value = str(df["acquisition_time"].iloc[0])
            if not acq_value:
                acq_value = manifest_times.get(str(match_csv.resolve()))
            if not acq_value:
                self.last_skipped_samples += 1
                continue

            try:
                acq_dt = pd.to_datetime(acq_value, utc=True, errors="raise").to_pydatetime()
            except Exception as exc:
                _ = exc
                self.last_skipped_samples += 1
                continue

            sample_record = {
                "sample": sample_name,
                "acquisition_time": acq_dt,
                "acquisition_time_iso": acq_dt.isoformat(),
                "match_csv": match_csv,
                "trace_csv": trace_csv,
                "compounds": {},
            }

            if not df.empty and "compound_name" in df.columns:
                for _, row in df.iterrows():
                    compound_name = str(row.get("compound_name", "")).strip()
                    if not compound_name:
                        continue

                    observed_mz = pd.to_numeric(row.get("observed_mz"), errors="coerce")
                    observed_rt = pd.to_numeric(row.get("observed_rt"), errors="coerce")
                    intensity = pd.to_numeric(row.get("intensity"), errors="coerce")
                    area = pd.to_numeric(row.get("area"), errors="coerce")
                    target_mz = pd.to_numeric(row.get("target_mz"), errors="coerce")
                    target_rt = pd.to_numeric(row.get("target_rt"), errors="coerce")
                    mz_error_ppm = pd.to_numeric(row.get("mz_error_ppm"), errors="coerce")
                    rt_error = pd.to_numeric(row.get("rt_error"), errors="coerce")
                    mf_id_val = pd.to_numeric(row.get("mf_id"), errors="coerce")
                    if pd.isna(mf_id_val):
                        continue
                    mf_id = int(mf_id_val)
                    trace_col = self._safe_trace_col(mf_id, compound_name)

                    metric = {
                        "observed_mz": float(observed_mz) if not pd.isna(observed_mz) else None,
                        "observed_rt": float(observed_rt) if not pd.isna(observed_rt) else None,
                        "intensity": float(intensity) if not pd.isna(intensity) else None,
                        "area": float(area) if not pd.isna(area) else None,
                        "target_mz": float(target_mz) if not pd.isna(target_mz) else None,
                        "target_rt": float(target_rt) if not pd.isna(target_rt) else None,
                        "mz_error_ppm": float(mz_error_ppm) if not pd.isna(mz_error_ppm) else None,
                        "rt_error": float(rt_error) if not pd.isna(rt_error) else None,
                        "mf_id": mf_id,
                        "trace_col": trace_col,
                    }
                    sample_record["compounds"][compound_name] = metric

                    if compound_name not in compounds:
                        compounds[compound_name] = {
                            "name": compound_name,
                            "slug": self._slugify(compound_name),
                            "samples": [],
                            "detected_count": 0,
                        }

            samples.append(sample_record)

        samples.sort(key=lambda x: x["acquisition_time"])

        for compound_name, compound in compounds.items():
            for sample in samples:
                metric = sample["compounds"].get(compound_name)
                if metric:
                    compound["detected_count"] += 1
                compound["samples"].append(
                    {
                        "sample": sample["sample"],
                        "acquisition_time": sample["acquisition_time"],
                        "acquisition_time_iso": sample["acquisition_time_iso"],
                        "observed_mz": metric["observed_mz"] if metric else None,
                        "observed_rt": metric["observed_rt"] if metric else None,
                        "intensity": metric["intensity"] if metric else None,
                        "area": metric["area"] if metric else None,
                        "target_mz": metric["target_mz"] if metric else None,
                        "target_rt": metric["target_rt"] if metric else None,
                        "mz_error_ppm": metric["mz_error_ppm"] if metric else None,
                        "rt_error": metric["rt_error"] if metric else None,
                        "trace_csv": sample["trace_csv"],
                        "trace_col": metric["trace_col"] if metric else self._target_trace_col(compound_name),
                        "detected": bool(metric),
                    }
                )

        return samples, compounds, polarities

    @staticmethod
    def _first_number(values: list[float | None]) -> float | None:
        for value in values:
            if value is None:
                continue
            return float(value)
        return None

    @staticmethod
    def _min_max(values: list[float | None]) -> tuple[float, float] | tuple[None, None]:
        numeric = [float(v) for v in values if v is not None]
        if not numeric:
            return None, None
        return min(numeric), max(numeric)

    @staticmethod
    def _mean_cv(values: list[float | None]) -> tuple[float | None, float | None]:
        numeric = [float(v) for v in values if v is not None]
        if not numeric:
            return None, None
        series = pd.Series(numeric, dtype="float64")
        mean_val = float(series.mean())
        if mean_val == 0:
            return mean_val, None
        cv_percent = float((series.std(ddof=0) / abs(mean_val)) * 100.0)
        return mean_val, cv_percent

    @staticmethod
    def _mean_value(values: list[float | None]) -> float | None:
        """Return the arithmetic mean of non-None numeric values, or None."""
        numeric = [float(v) for v in values if v is not None]
        if not numeric:
            return None
        return float(sum(numeric) / len(numeric))

    def _build_landing_qc_plots(self, samples: list[dict], compounds: dict[str, dict]) -> tuple[dict, dict]:
        newest_sample_name = samples[-1]["sample"] if samples else None

        mz_range_x: list[float] = []
        mz_range_y: list[float] = []
        mz_range_plus: list[float] = []
        mz_range_minus: list[float] = []
        mz_range_custom: list[list[str | float]] = []
        mz_latest_x: list[float] = []
        mz_latest_y: list[float] = []
        mz_latest_custom: list[list[str | float]] = []

        rt_range_x: list[float] = []
        rt_range_y: list[float] = []
        rt_range_plus: list[float] = []
        rt_range_minus: list[float] = []
        rt_range_custom: list[list[str | float]] = []
        rt_latest_x: list[float] = []
        rt_latest_y: list[float] = []
        rt_latest_custom: list[list[str | float]] = []

        for compound_name in sorted(compounds):
            compound = compounds[compound_name]
            series = compound["samples"]
            if not series:
                continue

            target_mz = self._first_number([row.get("target_mz") for row in series])
            ppm_min, ppm_max = self._min_max([row.get("mz_error_ppm") for row in series])
            if target_mz is not None and ppm_min is not None and ppm_max is not None:
                mz_half_width = (target_mz * self.mz_tolerance_ppm) / 1e6
                ppm_center = (ppm_min + ppm_max) / 2.0
                mz_range_x.append(target_mz)
                mz_range_y.append(ppm_center)
                mz_range_plus.append(ppm_max - ppm_center)
                mz_range_minus.append(ppm_center - ppm_min)
                mz_range_custom.append(
                    [
                        compound["slug"],
                        compound_name,
                        target_mz,
                        target_mz - mz_half_width,
                        target_mz + mz_half_width,
                        ppm_min,
                        ppm_max,
                    ]
                )

            target_rt = self._first_number([row.get("target_rt") for row in series])
            rt_err_min, rt_err_max = self._min_max([row.get("rt_error") for row in series])
            if target_rt is not None and rt_err_min is not None and rt_err_max is not None:
                rt_err_center = (rt_err_min + rt_err_max) / 2.0
                rt_range_x.append(target_rt)
                rt_range_y.append(rt_err_center)
                rt_range_plus.append(rt_err_max - rt_err_center)
                rt_range_minus.append(rt_err_center - rt_err_min)
                rt_range_custom.append(
                    [
                        compound["slug"],
                        compound_name,
                        target_rt,
                        target_rt - self.rt_tolerance,
                        target_rt + self.rt_tolerance,
                        rt_err_min,
                        rt_err_max,
                    ]
                )

            if newest_sample_name is None:
                continue

            newest_row = next((row for row in series if row["sample"] == newest_sample_name), None)
            if newest_row is None:
                continue

            newest_mz = newest_row.get("observed_mz")
            newest_ppm = newest_row.get("mz_error_ppm")
            if newest_mz is not None and newest_ppm is not None:
                mz_latest_x.append(float(newest_mz))
                mz_latest_y.append(float(newest_ppm))
                mz_latest_custom.append([compound["slug"], compound_name, newest_sample_name])

            newest_rt = newest_row.get("target_rt")
            newest_rt_err = newest_row.get("rt_error")
            if newest_rt is not None and newest_rt_err is not None:
                rt_latest_x.append(float(newest_rt))
                rt_latest_y.append(float(newest_rt_err))
                rt_latest_custom.append([compound["slug"], compound_name, newest_sample_name])

        mz_plot = {
            "data": [
                {
                    "type": "scatter",
                    "mode": "markers",
                    "name": "Batch ppm range data",
                    "x": mz_range_x,
                    "y": mz_range_y,
                    "error_y": {
                        "type": "data",
                        "symmetric": False,
                        "array": mz_range_plus,
                        "arrayminus": mz_range_minus,
                        "thickness": 1.4,
                        "width": 0,
                        "color": "#2c7f6d",
                    },
                    "customdata": mz_range_custom,
                    "marker": {"size": 7, "color": "rgba(0,0,0,0)", "line": {"width": 0}},
                    "showlegend": False,
                    "hovertemplate": (
                        "Compound: %{customdata[1]}<br>"
                        "Target m/z: %{customdata[2]:.6f}<br>"
                        "Tolerance window: [%{customdata[3]:.6f}, %{customdata[4]:.6f}]<br>"
                        "ppm range: [%{customdata[5]:.3f}, %{customdata[6]:.3f}]<extra></extra>"
                    ),
                },
                {
                    "type": "scatter",
                    "mode": "markers",
                    "name": "Batch ppm range",
                    "x": [None],
                    "y": [None],
                    "hoverinfo": "skip",
                    "marker": {"size": 8, "color": "#2c7f6d"},
                },
                {
                    "type": "scatter",
                    "mode": "markers",
                    "name": "Newest sample",
                    "x": mz_latest_x,
                    "y": mz_latest_y,
                    "customdata": mz_latest_custom,
                    "marker": {"size": 9, "color": "#8a3d2b", "line": {"color": "#5f291d", "width": 1}},
                    "hovertemplate": (
                        "Compound: %{customdata[1]}<br>"
                        "Sample: %{customdata[2]}<br>"
                        "Observed m/z: %{x:.6f}<br>"
                        "ppm error: %{y:.3f}<extra></extra>"
                    ),
                },
            ],
            "layout": {
                "height": 380,
                "margin": {"l": 70, "r": 24, "t": 34, "b": 70},
                "showlegend": True,
                "title": {"text": "Mass accuracy overview"},
                "xaxis": {"title": "m/z (target on range markers; newest observed on dots)"},
                "yaxis": {
                    "title": "ppm error (batch min to max)",
                    "zeroline": True,
                    "range": [-self.mz_tolerance_ppm, self.mz_tolerance_ppm],
                },
            },
        }

        rt_plot = {
            "data": [
                {
                    "type": "scatter",
                    "mode": "markers",
                    "name": "Batch RT error range data",
                    "x": rt_range_x,
                    "y": rt_range_y,
                    "error_y": {
                        "type": "data",
                        "symmetric": False,
                        "array": rt_range_plus,
                        "arrayminus": rt_range_minus,
                        "thickness": 1.4,
                        "width": 0,
                        "color": "#3f9f8a",
                    },
                    "customdata": rt_range_custom,
                    "marker": {"size": 7, "color": "rgba(0,0,0,0)", "line": {"width": 0}},
                    "showlegend": False,
                    "hovertemplate": (
                        "Compound: %{customdata[1]}<br>"
                        "Target RT: %{customdata[2]:.4f} min<br>"
                        "Tolerance window: [%{customdata[3]:.4f}, %{customdata[4]:.4f}] min<br>"
                        "RT error range: [%{customdata[5]:.4f}, %{customdata[6]:.4f}] min<extra></extra>"
                    ),
                },
                {
                    "type": "scatter",
                    "mode": "markers",
                    "name": "Batch RT error range",
                    "x": [None],
                    "y": [None],
                    "hoverinfo": "skip",
                    "marker": {"size": 8, "color": "#3f9f8a"},
                },
                {
                    "type": "scatter",
                    "mode": "markers",
                    "name": "Newest sample",
                    "x": rt_latest_x,
                    "y": rt_latest_y,
                    "customdata": rt_latest_custom,
                    "marker": {"size": 9, "color": "#8a3d2b", "line": {"color": "#5f291d", "width": 1}},
                    "hovertemplate": (
                        "Compound: %{customdata[1]}<br>"
                        "Sample: %{customdata[2]}<br>"
                        "Target RT: %{x:.4f} min<br>"
                        "RT error: %{y:.4f} min<extra></extra>"
                    ),
                },
            ],
            "layout": {
                "height": 380,
                "margin": {"l": 70, "r": 24, "t": 34, "b": 70},
                "showlegend": True,
                "title": {"text": "Retention time overview"},
                "xaxis": {"title": "Retention time (target on range markers; newest observed on dots)"},
                "yaxis": {
                    "title": "RT error (batch min to max)",
                    "zeroline": True,
                    "range": [-self.rt_tolerance, self.rt_tolerance],
                },
            },
        }

        return mz_plot, rt_plot

    def _build_landing_qc_plots_untargeted(
        self,
        samples: list[dict],
        compounds: dict[str, dict],
    ) -> tuple[dict, dict]:
        """Untargeted landing-page overview plots.

        Anchors each feature at the per-feature batch-mean observed mz/rt
        instead of a truth value. Plots show deviation from that mean.
        """
        newest_sample_name = samples[-1]["sample"] if samples else None

        mz_range_x: list[float] = []
        mz_range_y: list[float] = []
        mz_range_plus: list[float] = []
        mz_range_minus: list[float] = []
        mz_range_custom: list[list[str | float]] = []
        mz_latest_x: list[float] = []
        mz_latest_y: list[float] = []
        mz_latest_custom: list[list[str | float]] = []

        rt_range_x: list[float] = []
        rt_range_y: list[float] = []
        rt_range_plus: list[float] = []
        rt_range_minus: list[float] = []
        rt_range_custom: list[list[str | float]] = []
        rt_latest_x: list[float] = []
        rt_latest_y: list[float] = []
        rt_latest_custom: list[list[str | float]] = []

        for compound_name in sorted(compounds):
            compound = compounds[compound_name]
            series = compound["samples"]
            if not series:
                continue

            detected_mz = [row.get("observed_mz") for row in series if row.get("observed_mz") is not None]
            detected_rt = [row.get("observed_rt") for row in series if row.get("observed_rt") is not None]
            mean_mz = self._mean_value(detected_mz)
            mean_rt = self._mean_value(detected_rt)

            if mean_mz is not None:
                ppm_devs = [
                    (float(v) - mean_mz) / mean_mz * 1e6 for v in detected_mz
                ]
                ppm_min, ppm_max = min(ppm_devs), max(ppm_devs)
                ppm_center = (ppm_min + ppm_max) / 2.0
                mz_half_width = (mean_mz * self.mz_tolerance_ppm) / 1e6
                mz_range_x.append(mean_mz)
                mz_range_y.append(ppm_center)
                mz_range_plus.append(ppm_max - ppm_center)
                mz_range_minus.append(ppm_center - ppm_min)
                mz_range_custom.append(
                    [
                        compound["slug"],
                        compound_name,
                        mean_mz,
                        mean_mz - mz_half_width,
                        mean_mz + mz_half_width,
                        ppm_min,
                        ppm_max,
                    ]
                )

            target_rt = self._first_number([row.get("target_rt") for row in series])

            if mean_rt is not None and target_rt is not None:
                rt_devs = [float(v) - mean_rt for v in detected_rt]
                rt_min, rt_max = min(rt_devs), max(rt_devs)
                rt_center = (rt_min + rt_max) / 2.0
                rt_range_x.append(float(target_rt))
                rt_range_y.append(rt_center)
                rt_range_plus.append(rt_max - rt_center)
                rt_range_minus.append(rt_center - rt_min)
                rt_range_custom.append(
                    [
                        compound["slug"],
                        compound_name,
                        mean_rt,
                        float(target_rt) - self.rt_tolerance,
                        float(target_rt) + self.rt_tolerance,
                        rt_min,
                        rt_max,
                    ]
                )

            if newest_sample_name is None:
                continue

            newest_row = next(
                (row for row in series if row["sample"] == newest_sample_name),
                None,
            )
            if newest_row is None:
                continue

            newest_mz = newest_row.get("observed_mz")
            if newest_mz is not None and mean_mz is not None:
                mz_latest_x.append(float(newest_mz))
                mz_latest_y.append((float(newest_mz) - mean_mz) / mean_mz * 1e6)
                mz_latest_custom.append(
                    [compound["slug"], compound_name, newest_sample_name]
                )

            newest_rt = newest_row.get("observed_rt")
            if newest_rt is not None and mean_rt is not None and target_rt is not None:
                rt_latest_x.append(float(target_rt))
                rt_latest_y.append(float(newest_rt) - mean_rt)
                rt_latest_custom.append(
                    [compound["slug"], compound_name, newest_sample_name]
                )

        mz_plot = {
            "data": [
                {
                    "type": "scatter",
                    "mode": "markers",
                    "name": "Batch ppm deviation range data",
                    "x": mz_range_x,
                    "y": mz_range_y,
                    "error_y": {
                        "type": "data",
                        "symmetric": False,
                        "array": mz_range_plus,
                        "arrayminus": mz_range_minus,
                        "thickness": 1.4,
                        "width": 0,
                        "color": "#2c7f6d",
                    },
                    "customdata": mz_range_custom,
                    "marker": {"size": 7, "color": "rgba(0,0,0,0)", "line": {"width": 0}},
                    "showlegend": False,
                    "hovertemplate": (
                        "Compound: %{customdata[1]}<br>"
                        "Batch-mean m/z: %{customdata[2]:.6f}<br>"
                        "Tolerance window: [%{customdata[3]:.6f}, %{customdata[4]:.6f}]<br>"
                        "ppm deviation range: [%{customdata[5]:.3f}, %{customdata[6]:.3f}]<extra></extra>"
                    ),
                },
                {
                    "type": "scatter",
                    "mode": "markers",
                    "name": "Batch ppm deviation range",
                    "x": [None],
                    "y": [None],
                    "hoverinfo": "skip",
                    "marker": {"size": 8, "color": "#2c7f6d"},
                },
                {
                    "type": "scatter",
                    "mode": "markers",
                    "name": "Newest sample",
                    "x": mz_latest_x,
                    "y": mz_latest_y,
                    "customdata": mz_latest_custom,
                    "marker": {"size": 9, "color": "#8a3d2b", "line": {"color": "#5f291d", "width": 1}},
                    "hovertemplate": (
                        "Compound: %{customdata[1]}<br>"
                        "Sample: %{customdata[2]}<br>"
                        "Observed m/z: %{x:.6f}<br>"
                        "ppm deviation: %{y:.3f}<extra></extra>"
                    ),
                },
            ],
            "layout": {
                "height": 380,
                "margin": {"l": 70, "r": 24, "t": 34, "b": 70},
                "showlegend": True,
                "title": {"text": "Mass accuracy overview (untargeted)"},
                "xaxis": {"title": "m/z (batch-mean anchor; newest observed on dots)"},
                "yaxis": {
                    "title": "ppm deviation from batch mean",
                    "zeroline": True,
                    "range": [-self.mz_tolerance_ppm, self.mz_tolerance_ppm],
                },
            },
        }

        rt_plot = {
            "data": [
                {
                    "type": "scatter",
                    "mode": "markers",
                    "name": "Batch RT deviation range data",
                    "x": rt_range_x,
                    "y": rt_range_y,
                    "error_y": {
                        "type": "data",
                        "symmetric": False,
                        "array": rt_range_plus,
                        "arrayminus": rt_range_minus,
                        "thickness": 1.4,
                        "width": 0,
                        "color": "#3f9f8a",
                    },
                    "customdata": rt_range_custom,
                    "marker": {"size": 7, "color": "rgba(0,0,0,0)", "line": {"width": 0}},
                    "showlegend": False,
                    "hovertemplate": (
                        "Compound: %{customdata[1]}<br>"
                        "Target RT: %{x:.4f} min<br>"
                        "Batch-mean RT: %{customdata[2]:.4f} min<br>"
                        "Tolerance window: [%{customdata[3]:.4f}, %{customdata[4]:.4f}] min<br>"
                        "RT deviation range: [%{customdata[5]:.4f}, %{customdata[6]:.4f}] min<extra></extra>"
                    ),
                },
                {
                    "type": "scatter",
                    "mode": "markers",
                    "name": "Batch RT deviation range",
                    "x": [None],
                    "y": [None],
                    "hoverinfo": "skip",
                    "marker": {"size": 8, "color": "#3f9f8a"},
                },
                {
                    "type": "scatter",
                    "mode": "markers",
                    "name": "Newest sample",
                    "x": rt_latest_x,
                    "y": rt_latest_y,
                    "customdata": rt_latest_custom,
                    "marker": {"size": 9, "color": "#8a3d2b", "line": {"color": "#5f291d", "width": 1}},
                    "hovertemplate": (
                        "Compound: %{customdata[1]}<br>"
                        "Sample: %{customdata[2]}<br>"
                        "Target RT: %{x:.4f} min<br>"
                        "RT deviation: %{y:.4f} min<extra></extra>"
                    ),
                },
            ],
            "layout": {
                "height": 380,
                "margin": {"l": 70, "r": 24, "t": 34, "b": 70},
                "showlegend": True,
                "title": {"text": "Retention time overview (untargeted)"},
                "xaxis": {"title": "Target retention time (min)"},
                "yaxis": {
                    "title": "RT deviation from batch mean (min)",
                    "zeroline": True,
                    "range": [-self.rt_tolerance, self.rt_tolerance],
                },
            },
        }

        return mz_plot, rt_plot

    def _collect_landing_cvs(
        self, compounds: dict[str, dict]
    ) -> tuple[list[float], list[float]]:
        """Return per-compound Intensity and Area CVs used on the landing page.

        Same ``_mean_cv`` definition as the compound index table. Compounds
        missing area values contribute only to the intensity series.
        """
        intensity_cvs: list[float] = []
        area_cvs: list[float] = []
        for compound_name in sorted(compounds):
            series = compounds[compound_name]["samples"]
            if not series:
                continue
            _, intensity_cv = self._mean_cv([row.get("intensity") for row in series])
            _, area_cv = self._mean_cv([row.get("area") for row in series])
            if intensity_cv is not None:
                intensity_cvs.append(float(intensity_cv))
            if area_cv is not None:
                area_cvs.append(float(area_cv))
        return intensity_cvs, area_cvs

    @staticmethod
    def _count_cv_below(cvs: list[float], threshold: float) -> tuple[int, int]:
        """Return (n below threshold, N with a computable CV)."""
        return sum(1 for cv in cvs if cv < threshold), len(cvs)

    @staticmethod
    def _format_cv_below_cell(n: int, total: int) -> str:
        """Return HTML: bold percent, then ``(n/N)``."""
        if total == 0:
            return "<strong>0%</strong> (0/0)"
        return f"<strong>{100.0 * n / total:.0f}%</strong> ({n}/{total})"

    def _render_cv_threshold_table(
        self, intensity_cvs: list[float], area_cvs: list[float]
    ) -> str:
        """HTML summary of compounds below 20% and 30% CV."""
        rows: list[str] = []
        for label, cvs in (("Intensity", intensity_cvs), ("Area", area_cvs)):
            n20, n_total = self._count_cv_below(cvs, 20.0)
            n30, _ = self._count_cv_below(cvs, 30.0)
            rows.append(
                "<tr>"
                f"<th scope='row'>{label}</th>"
                f"<td>{self._format_cv_below_cell(n20, n_total)}</td>"
                f"<td>{self._format_cv_below_cell(n30, n_total)}</td>"
                "</tr>"
            )
        body = "\n".join(rows)
        return (
            '<table class="cv-summary" id="landing-cv-summary">'
            "<thead><tr>"
            "<th></th><th>&lt; 20% CV</th><th>&lt; 30% CV</th>"
            "</tr></thead>"
            f"<tbody>{body}</tbody></table>"
        )

    def _build_landing_cv_histogram(self, compounds: dict[str, dict]) -> dict:
        """Build a dual overlaid histogram of per-compound Intensity and Area CV.

        Uses the same ``_mean_cv`` definition as the compound index table.
        Compounds missing area values contribute only to the intensity series.
        """
        intensity_cvs, area_cvs = self._collect_landing_cvs(compounds)

        all_cvs = intensity_cvs + area_cvs
        bin_size = 5.0
        if all_cvs:
            x_max = max(all_cvs)
            # Pad to the next bin boundary so the largest value is fully inside.
            x_end = max(bin_size, (int(x_max / bin_size) + 1) * bin_size)
        else:
            x_end = 50.0

        xbins = {"start": 0.0, "end": float(x_end), "size": bin_size}
        data: list[dict] = [
            {
                "type": "histogram",
                "name": "Intensity CV",
                "x": intensity_cvs,
                "opacity": 0.55,
                "marker": {"color": "#8a3d2b"},
                "xbins": xbins,
                "hovertemplate": "Intensity CV bin: %{x}<br>Count: %{y}<extra></extra>",
            },
            {
                "type": "histogram",
                "name": "Area CV",
                "x": area_cvs,
                "opacity": 0.55,
                "marker": {"color": "#2c7f6d"},
                "xbins": xbins,
                "hovertemplate": "Area CV bin: %{x}<br>Count: %{y}<extra></extra>",
            },
        ]

        return {
            "data": data,
            "layout": {
                "height": 380,
                "margin": {"l": 70, "r": 24, "t": 34, "b": 70},
                "barmode": "overlay",
                "showlegend": True,
                "title": {"text": "Reproducibility overview (CV)"},
                "xaxis": {
                    "title": "CV (%)",
                    "range": [0, float(x_end)],
                },
                "yaxis": {"title": "Number of compounds"},
                "shapes": [
                    {
                        "type": "line",
                        "x0": 30,
                        "x1": 30,
                        "y0": 0,
                        "y1": 1,
                        "yref": "paper",
                        "line": {
                            "color": "#b42318",
                            "width": 1.5,
                            "dash": "dash",
                        },
                    }
                ],
                "annotations": [
                    {
                        "x": 30,
                        "y": 1,
                        "yref": "paper",
                        "text": "30% threshold",
                        "showarrow": False,
                        "xanchor": "left",
                        "yanchor": "bottom",
                        "font": {"size": 11, "color": "#b42318"},
                        "xshift": 4,
                    }
                ],
            },
        }

    def _render_index(
        self,
        samples: list[dict],
        compounds: dict[str, dict],
        generated_at: str,
        polarity_label: str,
    ) -> str:
        rows = []
        for compound_name in sorted(compounds):
            c = compounds[compound_name]
            series = c["samples"]
            ppm_values = [row.get("mz_error_ppm") for row in series]
            rt_error_values = [row.get("rt_error") for row in series]
            intensity_values = [row.get("intensity") for row in series]
            area_values = [row.get("area") for row in series]

            avg_ppm, _ = self._mean_cv(ppm_values)
            avg_rt_error, _ = self._mean_cv(rt_error_values)
            _, intensity_cv = self._mean_cv(intensity_values)
            _, area_cv = self._mean_cv(area_values)

            target_mz = self._first_number([row.get("target_mz") for row in series])
            target_rt = self._first_number([row.get("target_rt") for row in series])

            target_mz_text = f"{target_mz:.4f}" if target_mz is not None else "n/a"
            target_rt_text = f"{target_rt:.3f}" if target_rt is not None else "n/a"
            avg_ppm_text = f"{avg_ppm:.3f}" if avg_ppm is not None else "n/a"
            avg_rt_error_text = f"{avg_rt_error:.4f}" if avg_rt_error is not None else "n/a"
            intensity_cv_text = f"{intensity_cv:.2f}%" if intensity_cv is not None else "n/a"
            intensity_cv_style = " style='color:#b42318;font-weight:700;'" if intensity_cv is not None and intensity_cv > 30.0 else ""
            area_cv_text = f"{area_cv:.2f}%" if area_cv is not None else "n/a"
            area_cv_style = " style='color:#b42318;font-weight:700;'" if area_cv is not None and area_cv > 30.0 else ""

            rows.append(
                "<tr>"
                f"<td><a href='compounds/{escape(c['slug'])}.html'>{escape(c['name'])}</a></td>"
                f"<td>{target_mz_text}</td>"
                f"<td>{target_rt_text}</td>"
                f"<td>{c.get('detected_count', len(c['samples']))}</td>"
                f"<td>{avg_ppm_text}</td>"
                f"<td>{avg_rt_error_text}</td>"
                f"<td{intensity_cv_style}>{intensity_cv_text}</td>"
                f"<td{area_cv_style}>{area_cv_text}</td>"
                "</tr>"
            )

        table_rows = "\n".join(rows) if rows else "<tr><td colspan='8'>No compounds detected yet.</td></tr>"
        if self.untargeted_mode:
            mz_plot, rt_plot = self._build_landing_qc_plots_untargeted(
                samples=samples, compounds=compounds
            )
        else:
            mz_plot, rt_plot = self._build_landing_qc_plots(
                samples=samples, compounds=compounds
            )
        cv_plot = self._build_landing_cv_histogram(compounds)
        intensity_cvs, area_cvs = self._collect_landing_cvs(compounds)
        cv_summary_html = self._render_cv_threshold_table(intensity_cvs, area_cvs)
        cv_json = json.dumps(cv_plot)
        mz_json = json.dumps(mz_plot)
        rt_json = json.dumps(rt_plot)

        if self.untargeted_mode:
            _avg_ppm_tooltip = "error vs untargeted-search-space mz (set by the seed sample)"
            _avg_rt_tooltip = "error vs untargeted-search-space rt (set by the seed sample)"
            _target_mz_label = "Target m/z"
            _target_rt_label = "Target RT (min)"
            _target_mz_tooltip = "m/z from the untargeted-search-space CSV (set by the seed sample)"
            _target_rt_tooltip = "RT from the untargeted-search-space CSV (set by the seed sample)"
        else:
            _avg_ppm_tooltip = "error vs target"
            _avg_rt_tooltip = "error vs target"
            _target_mz_label = "Target m/z"
            _target_rt_label = "Target RT (min)"
            _target_mz_tooltip = "m/z from the standards CSV"
            _target_rt_tooltip = "retention time from the standards CSV"

        return f"""<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>MetabWatch Compound Index</title>
    <script src=\"{escape(PLOTLY_JS_FILENAME)}\"></script>
  <style>
    :root {{
      --bg: #f6f7f2;
      --panel: #ffffff;
      --ink: #1f2623;
      --line: #dde3dc;
      --accent: #24584b;
    }}
    body {{
      margin: 0;
      padding: 24px;
      background: radial-gradient(circle at top right, #e4f1eb, var(--bg));
      color: var(--ink);
      font-family: \"Avenir Next\", \"Segoe UI\", sans-serif;
    }}
    .card {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 14px;
      padding: 20px;
      box-shadow: 0 8px 22px rgba(17, 24, 39, 0.08);
      max-width: 1280px;
      margin: 0 auto;
    }}
    a {{ color: var(--accent); text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    table {{ width: 100%; border-collapse: collapse; }}
    th, td {{ padding: 10px; border-bottom: 1px solid var(--line); text-align: left; }}
    th {{ background: #f0f4ef; }}
    .cv-overview {{
      display: flex;
      align-items: center;
      gap: 24px;
    }}
    #landing-cv {{ flex: 1 1 0; min-width: 0; }}
    table.cv-summary {{
      width: auto;
      flex: 0 0 auto;
      margin: 0;
      white-space: nowrap;
    }}
    table.cv-summary th[scope="row"] {{ background: #f0f4ef; font-weight: 600; }}
    @media (max-width: 900px) {{
      .cv-overview {{ flex-direction: column; align-items: stretch; }}
      table.cv-summary {{ align-self: flex-start; }}
    }}
        .section-title {{ margin: 22px 0 10px; }}
        .meta-polarity {{ margin: 4px 0 12px; color: #47524d; }}
  </style>
</head>
<body>
  <section class=\"card\">
    <h1>MetabWatch Compound Index</h1>
    <p>Generated: {escape(generated_at)}</p>
    {self._polarity_meta_html(polarity_label)}

        <h2 class=\"section-title\">Reproducibility overview (CV)</h2>
        <div class=\"cv-overview\">
          <div id=\"landing-cv\"></div>
          {cv_summary_html}
        </div>

        <h2 class=\"section-title\">Mass accuracy overview</h2>
        <div id=\"landing-mz\"></div>

        <h2 class=\"section-title\">Retention time overview</h2>
        <div id=\"landing-rt\"></div>

        <h2 class=\"section-title\">Compound Index</h2>
    <table>
      <thead>
                <tr>
                    <th>Compound</th>
                    <th title="{escape(_target_mz_tooltip)}">{escape(_target_mz_label)}</th>
                    <th title="{escape(_target_rt_tooltip)}">{escape(_target_rt_label)}</th>
                    <th>Detected Samples</th>
                    <th title="{escape(_avg_ppm_tooltip)}">Avg ppm</th>
                    <th title="{escape(_avg_rt_tooltip)}">Avg RT Error (min)</th>
                    <th>Intensity CV</th>
                    <th>Area CV</th>
                </tr>
      </thead>
      <tbody>
        {table_rows}
      </tbody>
    </table>
  </section>
    <script>
        const cvPlot = {cv_json};
        const mzPlot = {mz_json};
        const rtPlot = {rt_json};
        Plotly.newPlot('landing-cv', cvPlot.data, cvPlot.layout, {{responsive: true}});
        Plotly.newPlot('landing-mz', mzPlot.data, mzPlot.layout, {{responsive: true}});
        Plotly.newPlot('landing-rt', rtPlot.data, rtPlot.layout, {{responsive: true}});
    </script>
</body>
</html>
"""

    @staticmethod
    def _line_color(index: int, total: int) -> str:
        """Return grayscale color with newest sample darkest."""
        if total <= 1:
            shade = 40
        else:
            shade = int(210 - (index / (total - 1)) * 170)
        shade = max(35, min(220, shade))
        return f"rgb({shade},{shade},{shade})"

    def _render_compound_page(
        self,
        compound: dict,
        generated_at: str,
        polarity_label: str,
    ) -> str:
        series = compound["samples"]
        full_samples = [row["sample"] for row in series]
        samples = [self._acquisition_label(row["acquisition_time_iso"]) for row in series]
        ppm_values = [row.get("mz_error_ppm") for row in series]
        rt_values = [row["observed_rt"] for row in series]
        rt_error_values = [row.get("rt_error") for row in series]
        intensity_values = [row["intensity"] for row in series]
        area_values = [row.get("area") for row in series]

        target_rt_values = [row.get("target_rt") for row in series if row.get("target_rt") is not None]
        target_rt = target_rt_values[0] if target_rt_values else None
        target_mz_values = [row.get("target_mz") for row in series if row.get("target_mz") is not None]
        target_mz = target_mz_values[0] if target_mz_values else None

        eic_traces = []
        for idx, row in enumerate(series):
            trace_csv = row["trace_csv"]
            trace_col = row["trace_col"]
            line_color = self._line_color(idx, len(series))
            try:
                trace_df = pd.read_csv(trace_csv)
            except Exception:
                continue

            if "time" not in trace_df.columns:
                continue

            times = pd.to_numeric(trace_df["time"], errors="coerce")
            if trace_col and trace_col in trace_df.columns:
                eic = pd.to_numeric(trace_df[trace_col], errors="coerce")
            elif self._target_trace_col(compound["name"]) in trace_df.columns:
                eic = pd.to_numeric(trace_df[self._target_trace_col(compound["name"])], errors="coerce")
            else:
                continue

            mask = (~times.isna()) & (~eic.isna())
            if not mask.any():
                continue

            # Overlay style follows the match CSV, not whether the mf_* EIC column
            # was exported. Target-m/z fallback chromatograms still get a solid
            # line and apex marker when intensity / observed_rt exist.
            match_detected = bool(row.get("detected")) and row.get("observed_rt") is not None

            eic_traces.append(
                {
                    "x": times[mask].tolist(),
                    "y": eic[mask].tolist(),
                    "name": self._acquisition_label(row["acquisition_time_iso"]),
                    "detected": match_detected,
                    "hovertemplate": (
                        "Sample: " + row["sample"] + "<br>"
                        +
                        (
                            "RT: %{x:.3f} min<br>EIC: %{y:.4g}<extra></extra>"
                            if match_detected
                            else "RT: %{x:.3f} min<br>EIC: %{y:.4g} (no detected peak)<extra></extra>"
                        )
                    ),
                    "line": {
                        "color": line_color,
                        "width": 1.8,
                        "dash": "dot" if not match_detected else "solid",
                    },
                }
            )

            picked_rt = row.get("observed_rt")
            if picked_rt is None or not match_detected:
                continue

            try:
                rt_value = float(picked_rt)
            except (TypeError, ValueError):
                continue

            valid_times = times[mask]
            valid_eic = eic[mask]
            if valid_times.empty or valid_eic.empty:
                continue

            nearest_idx = (valid_times - rt_value).abs().idxmin()
            picked_intensity = valid_eic.loc[nearest_idx]
            if pd.isna(picked_intensity):
                continue

            eic_traces.append(
                {
                    "x": [rt_value],
                    "y": [float(picked_intensity)],
                    "name": self._acquisition_label(row["acquisition_time_iso"]) + " peak",
                    "showlegend": False,
                    "mode": "markers",
                    "type": "scatter",
                    "hovertemplate": (
                        "Sample: " + row["sample"] + "<br>"
                        "Picked peak RT: %{x:.3f} min<br>"
                        "Picked peak EIC: %{y:.4g}<extra></extra>"
                    ),
                    "marker": {
                        "size": 8,
                        "color": "#f5f5f5",
                        "line": {"color": "#1a1a1a", "width": 1.4},
                    },
                }
            )

        ppm_mean, ppm_cv = self._mean_cv(ppm_values)
        rt_mean, rt_cv = self._mean_cv(rt_values)
        intensity_mean, intensity_cv = self._mean_cv(intensity_values)
        area_mean, area_cv = self._mean_cv(area_values)

        ppm_summary = (
            f"Avg ppm: {ppm_mean:.3f}<br>PPM CV: {ppm_cv:.2f}%"
            if ppm_mean is not None and ppm_cv is not None
            else "Avg ppm: n/a<br>PPM CV: n/a"
        )
        rt_summary = (
            f"Avg RT: {rt_mean:.4f} min<br>RT CV: {rt_cv:.2f}%"
            if rt_mean is not None and rt_cv is not None
            else "Avg RT: n/a<br>RT CV: n/a"
        )
        intensity_summary = (
            f"Avg intensity: {intensity_mean:.4g}<br>Intensity CV: {intensity_cv:.2f}%"
            if intensity_mean is not None and intensity_cv is not None
            else "Avg intensity: n/a<br>Intensity CV: n/a"
        )
        area_summary = (
            f"Avg area: {area_mean:.4g}<br>Area CV: {area_cv:.2f}%"
            if area_mean is not None and area_cv is not None
            else "Avg area: n/a<br>Area CV: n/a"
        )

        shapes = [
            {
                "type": "line",
                "xref": "x",
                "yref": "y",
                "x0": samples[0] if samples else 0,
                "x1": samples[-1] if samples else 1,
                "y0": 0,
                "y1": 0,
                "line": {"color": "#8a3d2b", "width": 1.2, "dash": "dot"},
            },
            {
                "type": "line",
                "xref": "x",
                "yref": "y2",
                "x0": samples[0] if samples else 0,
                "x1": samples[-1] if samples else 1,
                "y0": 0,
                "y1": 0,
                "line": {"color": "#8a3d2b", "width": 1.2, "dash": "dot"},
            },
        ]

        annotations = [
            {
                "xref": "paper",
                "yref": "paper",
                "x": 0.99,
                "y": 0.99,
                "xanchor": "right",
                "yanchor": "top",
                "align": "right",
                "showarrow": False,
                "bgcolor": "rgba(255,255,255,0.82)",
                "bordercolor": "#dde3dc",
                "borderwidth": 1,
                "text": ppm_summary,
                "font": {"size": 11},
            },
            {
                "xref": "paper",
                "yref": "paper",
                "x": 0.99,
                "y": 0.65,
                "xanchor": "right",
                "yanchor": "top",
                "align": "right",
                "showarrow": False,
                "bgcolor": "rgba(255,255,255,0.82)",
                "bordercolor": "#dde3dc",
                "borderwidth": 1,
                "text": rt_summary,
                "font": {"size": 11},
            },
            {
                "xref": "paper",
                "yref": "paper",
                "x": 0.99,
                "y": 0.31,
                "xanchor": "right",
                "yanchor": "top",
                "align": "right",
                "showarrow": False,
                "bgcolor": "rgba(255,255,255,0.82)",
                "bordercolor": "#dde3dc",
                "borderwidth": 1,
                "text": intensity_summary + "<br>" + area_summary,
                "font": {"size": 11},
            },
        ]

        top_plot = {
            "data": [
                {
                    "type": "scatter",
                    "mode": "lines+markers",
                    "name": "PPM error",
                    "x": samples,
                    "y": ppm_values,
                    "customdata": full_samples,
                    "hovertemplate": (
                        "Sample: %{customdata}<br>"
                        "PPM error: %{y:.3f}<extra></extra>"
                    ),
                    "xaxis": "x",
                    "yaxis": "y",
                    "line": {"color": "#2c7f6d"},
                    "marker": {"size": 8, "color": "#2c7f6d"},
                },
                {
                    "type": "scatter",
                    "mode": "lines+markers",
                    "name": "RT error",
                    "x": samples,
                    "y": rt_error_values,
                    "customdata": full_samples,
                    "hovertemplate": (
                        "Sample: %{customdata}<br>"
                        "RT error: %{y:.4f} min<extra></extra>"
                    ),
                    "xaxis": "x",
                    "yaxis": "y2",
                    "line": {"color": "#3f9f8a"},
                    "marker": {"size": 8, "color": "#3f9f8a"},
                },
                {
                    "type": "bar",
                    "name": "Intensity",
                    "x": samples,
                    "y": intensity_values,
                    "customdata": full_samples,
                    "hovertemplate": (
                        "Sample: %{customdata}<br>"
                        "Intensity: %{y:.4g}<extra></extra>"
                    ),
                    "xaxis": "x",
                    "yaxis": "y3",
                    "marker": {"color": "#5bb8a2"},
                },
            ],
            "layout": {
                "height": 760,
                "showlegend": False,
                "margin": {"l": 90, "r": 20, "t": 40, "b": 110},
                "shapes": shapes,
                "annotations": annotations,
                "xaxis": {
                    "anchor": "y3",
                    "side": "bottom",
                    "title": "Acquired Time (UTC)",
                    "tickangle": -15,
                    "type": "category",
                    "categoryorder": "array",
                    "categoryarray": samples,
                    "tickfont": {"size": 11},
                    "automargin": True,
                },
                "yaxis": {
                    "title": {"text": "PPM error", "standoff": 8},
                    "automargin": True,
                    "domain": [0.72, 1.0],
                    "range": [-self.mz_tolerance_ppm, self.mz_tolerance_ppm],
                },
                "yaxis2": {
                    "title": {"text": "RT error (min)", "standoff": 8},
                    "automargin": True,
                    "domain": [0.38, 0.66],
                    "range": [-self.rt_tolerance, self.rt_tolerance],
                },
                "yaxis3": {
                    "title": {"text": "Intensity", "standoff": 8},
                    "automargin": True,
                    "domain": [0.04, 0.32],
                },
            },
        }

        eic_x_range = [target_rt - 2.0, target_rt + 2.0] if target_rt is not None else None
        eic_window_max = 0.0
        non_detect_indices: list[int] = []
        for trace_index, trace in enumerate(eic_traces):
            if not bool(trace.get("detected", True)):
                non_detect_indices.append(trace_index)
            x_vals = trace.get("x", [])
            y_vals = trace.get("y", [])
            for x_val, y_val in zip(x_vals, y_vals):
                if y_val is None:
                    continue
                if eic_x_range is not None and (x_val < eic_x_range[0] or x_val > eic_x_range[1]):
                    continue
                if y_val > eic_window_max:
                    eic_window_max = float(y_val)

        for trace in eic_traces:
            trace.pop("detected", None)

        eic_y_range = [0.0, eic_window_max * 1.05] if eic_window_max > 0 else [0.0, 1.0]

        eic_plot = {
            "data": eic_traces,
            "layout": {
                "height": 420,
                "showlegend": True,
                "legend": {"orientation": "h", "y": 1.1},
                "margin": {"l": 70, "r": 20, "t": 40, "b": 60},
                "xaxis": {
                    "title": "Retention time (min)",
                    "range": eic_x_range,
                },
                "yaxis": {"title": "EIC intensity", "range": eic_y_range},
            },
        }

        top_json = json.dumps(top_plot)
        eic_json = json.dumps(eic_plot)

        _anchor_label = "Seed (untargeted)" if self.untargeted_mode else "Target"
        _target_mz_text = f"{target_mz:.4f}" if target_mz is not None else "n/a"
        _target_rt_text = f"{target_rt:.3f}" if target_rt is not None else "n/a"

        return f"""<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>Compound Dashboard | {escape(compound['name'])}</title>
  <script src=\"../{escape(PLOTLY_JS_FILENAME)}\"></script>
  <style>
    :root {{
      --bg: #f6f7f2;
      --panel: #ffffff;
      --ink: #1f2623;
      --line: #dde3dc;
      --accent: #24584b;
    }}
    body {{
      margin: 0;
      padding: 24px;
      background: radial-gradient(circle at top right, #e4f1eb, var(--bg));
      color: var(--ink);
      font-family: \"Avenir Next\", \"Segoe UI\", sans-serif;
    }}
    .card {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 14px;
      padding: 20px;
      box-shadow: 0 8px 22px rgba(17, 24, 39, 0.08);
      max-width: 1200px;
      margin: 0 auto;
    }}
    .meta {{ margin-bottom: 14px; color: #47524d; }}
    .meta-polarity {{ margin: 4px 0 12px; color: #47524d; }}
    .section-title {{ margin: 20px 0 8px; }}
    a {{ color: var(--accent); text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
  </style>
</head>
<body>
  <section class=\"card\">
    <p><a href=\"../dashboard.html\">Back to compound index</a></p>
    <h1>{escape(compound['name'])}</h1>
    <p class=\"meta\">{escape(_anchor_label)}: m/z {escape(_target_mz_text)} &middot; RT {escape(_target_rt_text)} min &middot; detected in {len(series)} sample(s). Generated: {escape(generated_at)}</p>
    {self._polarity_meta_html(polarity_label)}

    <h2 class=\"section-title\">Across-sample metrics</h2>
    <div id=\"top-plot\"></div>

    <h2 class=\"section-title\">EIC overlay (most recent darkest)</h2>
    <div id=\"eic-plot\"></div>
  </section>

  <script>
    const topPlot = {top_json};
    const eicPlot = {eic_json};
    Plotly.newPlot('top-plot', topPlot.data, topPlot.layout, {{responsive: true}});
    Plotly.newPlot('eic-plot', eicPlot.data, eicPlot.layout, {{responsive: true}});
  </script>
</body>
</html>
"""

    def _export_wide_csvs(
        self,
        samples: list[dict],
        compounds: dict[str, dict],
    ) -> dict[str, Path]:
        """Write wide-style pivot CSVs (feature rows × sample columns).

        Produces four files next to the dashboard:

        - ``export_mz.csv`` — observed m/z per sample
        - ``export_rt.csv`` — observed retention time (min) per sample
        - ``export_height.csv`` — peak maximum intensity (height) per sample
        - ``export_area.csv`` — integrated peak area per sample

        Parameters
        ----------
        samples : list[dict]
            Ordered sample records (columns follow this order).
        compounds : dict[str, dict]
            Compound records keyed by compound name.

        Returns
        -------
        dict[str, Path]
            Mapping of export label (``mz``, ``rt``, ``height``, ``area``) to written path.
        """
        sample_names = [sample["sample"] for sample in samples]
        metric_fields = {
            "mz": "observed_mz",
            "rt": "observed_rt",
            "height": "intensity",
            "area": "area",
        }
        export_dir = self.html_output.parent
        written: dict[str, Path] = {}

        for label, field in metric_fields.items():
            rows: list[dict] = []
            for compound_name in sorted(compounds):
                compound = compounds[compound_name]
                by_sample = {
                    row["sample"]: row.get(field) for row in compound["samples"]
                }
                row_out: dict = {"compound_name": compound_name}
                for sample_name in sample_names:
                    row_out[sample_name] = by_sample.get(sample_name)
                rows.append(row_out)

            columns = ["compound_name", *sample_names]
            df = pd.DataFrame(rows, columns=columns)
            out_path = export_dir / f"export_{label}.csv"
            self._write_atomic_csv(out_path, df)
            written[label] = out_path

        return written

    def render(self) -> Path:
        """Render landing index, per-compound pages, and wide CSV exports.

        Returns
        -------
        Path
            Path to the generated landing dashboard HTML.
        """
        generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        samples, compounds, polarities = self._build_dataset()
        polarity_label = self.format_run_polarity_label(polarities)
        self.last_polarity_label = polarity_label

        self._ensure_plotly_asset()

        index_html = self._render_index(
            samples=samples,
            compounds=compounds,
            generated_at=generated_at,
            polarity_label=polarity_label,
        )
        self._write_atomic(self.html_output, index_html)

        compounds_dir = self.html_output.parent / "compounds"
        for compound_name in sorted(compounds):
            compound = compounds[compound_name]
            page_html = self._render_compound_page(
                compound=compound,
                generated_at=generated_at,
                polarity_label=polarity_label,
            )
            self._write_atomic(compounds_dir / f"{compound['slug']}.html", page_html)

        self.last_export_paths = self._export_wide_csvs(samples=samples, compounds=compounds)
        self.last_compound_pages = len(compounds)
        return self.html_output
