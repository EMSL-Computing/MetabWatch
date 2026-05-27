from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from html import escape
from pathlib import Path

import pandas as pd


class HTMLSynthesizer:
    """Generate a compound index and one dashboard page per detected compound.

    Parameters
    ----------
    output_dirs : tuple[Path, ...]
        Directories to search for per-sample output CSV files.
    html_output : Path
        Landing index path (`dashboard.html`).
    """

    def __init__(self, output_dirs: tuple[Path, ...], html_output: Path):
        self.output_dirs = output_dirs
        self.html_output = html_output
        self.last_compound_pages: int = 0
        self.last_skipped_samples: int = 0

    @staticmethod
    def _slugify(name: str) -> str:
        slug = re.sub(r"[^0-9A-Za-z]+", "-", name).strip("-").lower()
        return slug or "compound"

    @staticmethod
    def _safe_trace_col(mf_id: int, compound_name: str) -> str:
        safe_name = re.sub(r"[^0-9A-Za-z]+", "_", compound_name).strip("_")
        return f"mf_{mf_id}_{safe_name}" if safe_name else f"mf_{mf_id}"

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

    def _build_dataset(self) -> tuple[list[dict], dict[str, dict]]:
        """Build sample and compound records from matches and traces CSV files."""
        manifest_times = self._collect_manifest_acquisition_times()
        samples: list[dict] = []
        compounds: dict[str, dict] = {}
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
                    target_mz = pd.to_numeric(row.get("target_mz"), errors="coerce")
                    target_rt = pd.to_numeric(row.get("target_rt"), errors="coerce")
                    mf_id_val = pd.to_numeric(row.get("mf_id"), errors="coerce")
                    if pd.isna(mf_id_val):
                        continue
                    mf_id = int(mf_id_val)
                    trace_col = self._safe_trace_col(mf_id, compound_name)

                    metric = {
                        "observed_mz": float(observed_mz) if not pd.isna(observed_mz) else None,
                        "observed_rt": float(observed_rt) if not pd.isna(observed_rt) else None,
                        "intensity": float(intensity) if not pd.isna(intensity) else None,
                        "target_mz": float(target_mz) if not pd.isna(target_mz) else None,
                        "target_rt": float(target_rt) if not pd.isna(target_rt) else None,
                        "mf_id": mf_id,
                        "trace_col": trace_col,
                    }
                    sample_record["compounds"][compound_name] = metric

                    if compound_name not in compounds:
                        compounds[compound_name] = {
                            "name": compound_name,
                            "slug": self._slugify(compound_name),
                            "samples": [],
                        }

            samples.append(sample_record)

        samples.sort(key=lambda x: x["acquisition_time"])

        for compound_name, compound in compounds.items():
            for sample in samples:
                metric = sample["compounds"].get(compound_name)
                if not metric:
                    continue
                compound["samples"].append(
                    {
                        "sample": sample["sample"],
                        "acquisition_time": sample["acquisition_time"],
                        "acquisition_time_iso": sample["acquisition_time_iso"],
                        "observed_mz": metric["observed_mz"],
                        "observed_rt": metric["observed_rt"],
                        "intensity": metric["intensity"],
                        "target_mz": metric["target_mz"],
                        "target_rt": metric["target_rt"],
                        "trace_csv": sample["trace_csv"],
                        "trace_col": metric["trace_col"],
                    }
                )

        return samples, compounds

    def _render_index(self, compounds: dict[str, dict], generated_at: str) -> str:
        rows = []
        for compound_name in sorted(compounds):
            c = compounds[compound_name]
            rows.append(
                "<tr>"
                f"<td><a href='compounds/{escape(c['slug'])}.html'>{escape(c['name'])}</a></td>"
                f"<td>{len(c['samples'])}</td>"
                "</tr>"
            )

        table_rows = "\n".join(rows) if rows else "<tr><td colspan='2'>No compounds detected yet.</td></tr>"

        return f"""<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>LCMS QC Compound Index</title>
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
      max-width: 980px;
      margin: 0 auto;
    }}
    a {{ color: var(--accent); text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    table {{ width: 100%; border-collapse: collapse; }}
    th, td {{ padding: 10px; border-bottom: 1px solid var(--line); text-align: left; }}
    th {{ background: #f0f4ef; }}
  </style>
</head>
<body>
  <section class=\"card\">
    <h1>LCMS QC Compound Index</h1>
    <p>Generated: {escape(generated_at)}</p>
    <table>
      <thead>
        <tr><th>Compound</th><th>Detected Samples</th></tr>
      </thead>
      <tbody>
        {table_rows}
      </tbody>
    </table>
  </section>
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

    def _render_compound_page(self, compound: dict, generated_at: str) -> str:
        series = compound["samples"]
        full_samples = [row["sample"] for row in series]
        samples = [self._acquisition_label(row["acquisition_time_iso"]) for row in series]
        mz_values = [row["observed_mz"] for row in series]
        rt_values = [row["observed_rt"] for row in series]
        intensity_values = [row["intensity"] for row in series]

        target_mz_values = [row.get("target_mz") for row in series if row.get("target_mz") is not None]
        target_rt_values = [row.get("target_rt") for row in series if row.get("target_rt") is not None]
        target_mz = target_mz_values[0] if target_mz_values else None
        target_rt = target_rt_values[0] if target_rt_values else None

        eic_traces = []
        for idx, row in enumerate(series):
            trace_csv = row["trace_csv"]
            trace_col = row["trace_col"]
            try:
                trace_df = pd.read_csv(trace_csv)
            except Exception:
                continue

            if "time" not in trace_df.columns or trace_col not in trace_df.columns:
                continue

            times = pd.to_numeric(trace_df["time"], errors="coerce")
            eic = pd.to_numeric(trace_df[trace_col], errors="coerce")
            mask = (~times.isna()) & (~eic.isna())
            if not mask.any():
                continue

            eic_traces.append(
                {
                    "x": times[mask].tolist(),
                    "y": eic[mask].tolist(),
                    "name": self._acquisition_label(row["acquisition_time_iso"]),
                    "hovertemplate": (
                        "Sample: " + row["sample"] + "<br>"
                        "RT: %{x:.3f} min<br>EIC: %{y:.4g}<extra></extra>"
                    ),
                    "line": {"color": self._line_color(idx, len(series)), "width": 1.8},
                }
            )

        shapes = []
        if target_mz is not None:
            shapes.append(
                {
                    "type": "line",
                    "xref": "x",
                    "yref": "y",
                    "x0": samples[0] if samples else 0,
                    "x1": samples[-1] if samples else 1,
                    "y0": target_mz,
                    "y1": target_mz,
                    "line": {"color": "#8a3d2b", "width": 1.2, "dash": "dot"},
                }
            )
        if target_rt is not None:
            shapes.append(
                {
                    "type": "line",
                    "xref": "x",
                    "yref": "y2",
                    "x0": samples[0] if samples else 0,
                    "x1": samples[-1] if samples else 1,
                    "y0": target_rt,
                    "y1": target_rt,
                    "line": {"color": "#8a3d2b", "width": 1.2, "dash": "dot"},
                }
            )

        top_plot = {
            "data": [
                {
                    "type": "scatter",
                    "mode": "lines+markers",
                    "name": "Observed m/z",
                    "x": samples,
                    "y": mz_values,
                    "customdata": full_samples,
                    "hovertemplate": (
                        "Sample: %{customdata}<br>"
                        "Observed m/z: %{y:.6f}<extra></extra>"
                    ),
                    "xaxis": "x",
                    "yaxis": "y",
                    "line": {"color": "#2c7f6d"},
                },
                {
                    "type": "scatter",
                    "mode": "lines+markers",
                    "name": "Observed RT",
                    "x": samples,
                    "y": rt_values,
                    "customdata": full_samples,
                    "hovertemplate": (
                        "Sample: %{customdata}<br>"
                        "Observed RT: %{y:.4f} min<extra></extra>"
                    ),
                    "xaxis": "x",
                    "yaxis": "y2",
                    "line": {"color": "#3f9f8a"},
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
                    "title": {"text": "Observed m/z", "standoff": 8},
                    "automargin": True,
                    "domain": [0.72, 1.0],
                    "range": [target_mz - 0.02, target_mz + 0.02] if target_mz is not None else None,
                },
                "yaxis2": {
                    "title": {"text": "Observed retention time", "standoff": 8},
                    "automargin": True,
                    "domain": [0.38, 0.66],
                    "range": [target_rt - 0.5, target_rt + 0.5] if target_rt is not None else None,
                },
                "yaxis3": {
                    "title": {"text": "Intensity", "standoff": 8},
                    "automargin": True,
                    "domain": [0.04, 0.32],
                },
            },
        }

        eic_plot = {
            "data": eic_traces,
            "layout": {
                "height": 420,
                "showlegend": True,
                "legend": {"orientation": "h", "y": 1.1},
                "margin": {"l": 70, "r": 20, "t": 40, "b": 60},
                "xaxis": {
                    "title": "Retention time (min)",
                    "range": [target_rt - 2.0, target_rt + 2.0] if target_rt is not None else None,
                },
                "yaxis": {"title": "EIC intensity"},
            },
        }

        top_json = json.dumps(top_plot)
        eic_json = json.dumps(eic_plot)

        return f"""<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>Compound Dashboard | {escape(compound['name'])}</title>
  <script src=\"https://cdn.plot.ly/plotly-2.35.2.min.js\"></script>
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
    .section-title {{ margin: 20px 0 8px; }}
    a {{ color: var(--accent); text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
  </style>
</head>
<body>
  <section class=\"card\">
    <p><a href=\"../dashboard.html\">Back to compound index</a></p>
    <h1>{escape(compound['name'])}</h1>
    <p class=\"meta\">Detected in {len(series)} sample(s). Generated: {escape(generated_at)}</p>

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

    def render(self) -> Path:
        """Render landing index and per-compound pages atomically.

        Returns
        -------
        Path
            Path to the generated landing dashboard HTML.
        """
        generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        samples, compounds = self._build_dataset()

        index_html = self._render_index(compounds=compounds, generated_at=generated_at)
        self._write_atomic(self.html_output, index_html)

        compounds_dir = self.html_output.parent / "compounds"
        for compound_name in sorted(compounds):
            compound = compounds[compound_name]
            page_html = self._render_compound_page(compound=compound, generated_at=generated_at)
            self._write_atomic(compounds_dir / f"{compound['slug']}.html", page_html)

        self.last_compound_pages = len(compounds)
        _ = samples  # keeps sample build explicit for future diagnostics
        return self.html_output
