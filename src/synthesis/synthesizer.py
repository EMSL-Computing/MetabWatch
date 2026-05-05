from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


class HTMLSynthesizer:
    def __init__(self, output_dirs: tuple[Path, ...], html_output: Path):
        self.output_dirs = output_dirs
        self.html_output = html_output

    def _collect_match_csvs(self) -> list[Path]:
        paths: list[Path] = []
        for output_dir in self.output_dirs:
            if not output_dir.exists():
                continue
            paths.extend(sorted(output_dir.glob("*_targeted_matches.csv")))
        return sorted(set(paths))

    def _collect_rows(self) -> list[dict[str, str]]:
        rows: list[dict[str, str]] = []
        for csv_path in self._collect_match_csvs():
            try:
                df = pd.read_csv(csv_path)
            except Exception:
                continue

            if df.empty:
                rows.append(
                    {
                        "sample": csv_path.name.replace("_targeted_matches.csv", ""),
                        "matches": "0",
                        "top_compounds": "",
                        "result_csv": str(csv_path),
                    }
                )
                continue

            compounds = []
            if "compound_name" in df.columns:
                compounds = sorted(set(df["compound_name"].astype(str).tolist()))[:8]

            rows.append(
                {
                    "sample": csv_path.name.replace("_targeted_matches.csv", ""),
                    "matches": str(len(df)),
                    "top_compounds": ", ".join(compounds),
                    "result_csv": str(csv_path),
                }
            )

        rows.sort(key=lambda r: r["sample"])
        return rows

    def render(self) -> Path:
        generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        rows = self._collect_rows()

        table_rows = "\n".join(
            (
                "<tr>"
                f"<td>{row['sample']}</td>"
                f"<td>{row['matches']}</td>"
                f"<td>{row['top_compounds']}</td>"
                f"<td><code>{row['result_csv']}</code></td>"
                "</tr>"
            )
            for row in rows
        )

        if not table_rows:
            table_rows = "<tr><td colspan='4'>No processed outputs yet.</td></tr>"

        html = f"""<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>LCMS QC Dashboard</title>
  <style>
    :root {{
      --bg: #f6f7f2;
      --panel: #ffffff;
      --ink: #1f2623;
      --accent: #2f6e5f;
      --line: #dde3dc;
    }}
    body {{
      margin: 0;
      padding: 24px;
      background: radial-gradient(circle at top right, #e4f1eb, var(--bg));
      color: var(--ink);
      font-family: "Avenir Next", "Segoe UI", sans-serif;
    }}
    .card {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 14px;
      padding: 20px;
      box-shadow: 0 8px 22px rgba(17, 24, 39, 0.08);
      max-width: 1100px;
      margin: 0 auto;
    }}
    h1 {{ margin-top: 0; }}
    table {{ width: 100%; border-collapse: collapse; }}
    th, td {{ padding: 10px; border-bottom: 1px solid var(--line); text-align: left; }}
    th {{ background: #f0f4ef; }}
  </style>
</head>
<body>
  <section class=\"card\">
    <h1>LCMS QC Dashboard</h1>
    <p>Generated: {generated_at}</p>
    <table>
      <thead>
        <tr><th>Sample</th><th>Matches</th><th>Top Compounds</th><th>Result CSV</th></tr>
      </thead>
      <tbody>
        {table_rows}
      </tbody>
    </table>
  </section>
</body>
</html>
"""

        self.html_output.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.html_output.with_suffix(self.html_output.suffix + ".tmp")
        tmp_path.write_text(html, encoding="utf-8")
        tmp_path.replace(self.html_output)
        return self.html_output
