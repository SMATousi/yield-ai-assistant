from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

import plotly.graph_objects as go

__all__ = ["ValidationWriter", "make_validation_writer"]


_FIGURE_FILENAMES: dict[str, str] = {
    "generate_doy_response_plot": "doy_response.html",
    "generate_recommendation_plot": "recommendation.html",
}


def _session_dir(root: Path) -> Path:
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    path = root / ts
    path.mkdir(parents=True, exist_ok=True)
    return path


def _esc(s: str) -> str:
    return (
        s.replace("&", "&amp;")
         .replace("<", "&lt;")
         .replace(">", "&gt;")
         .replace('"', "&quot;")
    )


class ValidationWriter:
    def __init__(self, session_dir: Path) -> None:
        self.session_dir = session_dir
        self._turns: list[dict] = []

    def write_turn(
        self,
        turn: int,
        query: str,
        response_text: str,
        raw_messages: list[dict],
        site: str | None,
        model: str,
        figures: dict[str, go.Figure],
    ) -> None:
        turn_dir = self.session_dir / f"{turn:03d}"
        turn_dir.mkdir(exist_ok=True)

        (turn_dir / "query.txt").write_text(query, encoding="utf-8")
        (turn_dir / "response.txt").write_text(response_text, encoding="utf-8")
        (turn_dir / "conversation.json").write_text(
            json.dumps(raw_messages, indent=2, default=str),
            encoding="utf-8",
        )

        written_figures: dict[str, str] = {}
        for tool_name, filename in _FIGURE_FILENAMES.items():
            if tool_name in figures:
                figures[tool_name].write_html(str(turn_dir / filename))
                written_figures[tool_name] = filename

        self._turns.append({
            "turn": turn,
            "ts": datetime.now().isoformat(timespec="seconds"),
            "query": query,
            "response": response_text,
            "site": site or "—",
            "model": model,
            "figures": written_figures,
        })
        self._write_index()

    def _write_index(self) -> None:
        rows: list[str] = []
        for t in self._turns:
            n = f"{t['turn']:03d}"
            doy_link = (
                f'<a href="{n}/doy_response.html" target="_blank">DOY</a>'
                if "generate_doy_response_plot" in t["figures"]
                else '<span class="missing">—</span>'
            )
            rec_link = (
                f'<a href="{n}/recommendation.html" target="_blank">Rec</a>'
                if "generate_recommendation_plot" in t["figures"]
                else '<span class="missing">—</span>'
            )
            rows.append(
                f"<tr>"
                f"<td>{n}</td>"
                f"<td>{t['ts']}</td>"
                f"<td>{_esc(t['query'])}</td>"
                f"<td class='response'>{_esc(t['response'])}</td>"
                f"<td>{t['site']}</td>"
                f"<td>{t['model']}</td>"
                f"<td>{doy_link}</td>"
                f"<td>{rec_link}</td>"
                f"</tr>"
            )

        last_conv = ""
        if self._turns:
            conv_path = (
                self.session_dir / f"{self._turns[-1]['turn']:03d}" / "conversation.json"
            )
            if conv_path.exists():
                last_conv = _esc(conv_path.read_text(encoding="utf-8"))

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Yield AI Validation — {_esc(self.session_dir.name)}</title>
<style>
  body {{ font-family: sans-serif; margin: 2em; color: #222; }}
  h1 {{ font-size: 1.4em; margin-bottom: 0.3em; }}
  .session {{ color: #666; font-size: 0.9em; margin-bottom: 1.5em; }}
  table {{ border-collapse: collapse; width: 100%; margin-bottom: 2em; }}
  th, td {{ border: 1px solid #ccc; padding: 6px 10px; text-align: left; vertical-align: top; }}
  th {{ background: #f0f0f0; }}
  td:nth-child(3) {{ max-width: 300px; word-break: break-word; }}
  td.response {{ max-width: 500px; white-space: pre-wrap; word-break: break-word; font-size: 0.85em; }}
  .missing {{ color: #aaa; }}
  a {{ color: #0066cc; }}
  h2 {{ font-size: 1.1em; margin-top: 2em; }}
  pre {{
    background: #f8f8f8; border: 1px solid #ddd; padding: 1em;
    overflow-x: auto; font-size: 0.8em; max-height: 600px; overflow-y: auto;
  }}
</style>
</head>
<body>
<h1>Yield AI — Validation Review</h1>
<div class="session">Session: <code>{_esc(str(self.session_dir))}</code></div>
<table>
  <thead>
    <tr>
      <th>#</th><th>Timestamp</th><th>Query</th><th>Response</th><th>Site</th><th>Model</th>
      <th>DOY Plot</th><th>Recommendation</th>
    </tr>
  </thead>
  <tbody>
    {"".join(rows)}
  </tbody>
</table>
<h2>Last turn — full conversation</h2>
<pre>{last_conv}</pre>
</body>
</html>"""

        (self.session_dir / "index.html").write_text(html, encoding="utf-8")


def make_validation_writer(validate: bool, root: Path | None = None) -> ValidationWriter | None:
    if not validate:
        return None
    effective_root = root or Path(os.getenv("YIELD_VALIDATE_DIR", "./validation_runs"))
    return ValidationWriter(session_dir=_session_dir(effective_root))
