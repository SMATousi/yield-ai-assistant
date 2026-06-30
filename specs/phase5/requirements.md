# Phase 5 — Hardening & Deployment: Requirements

## Functional Requirements

---

### FR-1: Validation Mode

Validation mode is an opt-in recording mode that captures every query, agent response, and generated figure for offline review by MU Extension agronomists. It is the primary mechanism for expert QA before production deployment.

**FR-1a: Activation**
- Activated by passing `--validate` on the command line or by setting `YIELD_VALIDATE=1` in the environment.
- When active, a non-dismissible `gr.Info` banner appears at the top of the Gradio UI reading `"Validation mode — all queries and figures are being saved to <output_dir>"`.
- The sidebar shows a read-only `gr.Textbox` labelled `"Saving to"` displaying the absolute path of the current output directory.

**FR-1b: Output directory**
- Root: `YIELD_VALIDATE_DIR` env var if set; otherwise `./validation_runs/` relative to the working directory.
- Each app launch creates a timestamped subdirectory: `<root>/<YYYY-MM-DD_HH-MM-SS>/`.
- Each query within a session creates a zero-padded turn subdirectory: `<session_dir>/<NNN>/` (e.g. `001/`, `002/`).

**FR-1c: Per-turn artifacts**
Each turn directory contains:
- `query.txt` — the raw user query string (not the augmented version).
- `response.txt` — the plain-language agent response text.
- `conversation.json` — the full LiteLLM message list for that turn (`raw_messages`), including tool calls and tool results, serialised as JSON. System messages are included.
- `doy_response.html` — the DOY response figure written via `figure.write_html()`. Only written if the figure was generated this turn.
- `recommendation.html` — the recommendation figure. Only written if generated this turn.

**FR-1d: Session index**
At the end of each turn, `<session_dir>/index.html` is regenerated. It is a static HTML file containing:
- A table with one row per completed turn: turn number, query text, resolved site, model used, timestamp.
- Each row links to `<NNN>/doy_response.html` and `<NNN>/recommendation.html` where those files exist; cells are greyed out where the figure was not generated.
- A `<pre>` block at the bottom showing the full `conversation.json` of the most recent turn.
- No external dependencies (no CDN links) — the HTML must render correctly when opened from the local filesystem.

**FR-1e: Validation writer module**
- `src/app/validation.py` — pure Python, no Gradio imports, no side effects at import time.
- `class ValidationWriter` with:
  - `__init__(self, session_dir: Path)` — creates the session directory.
  - `write_turn(self, turn: int, query: str, response_text: str, raw_messages: list[dict], site: str | None, model: str, figures: dict[str, go.Figure]) -> None` — writes all per-turn artifacts and regenerates `index.html`.
- `make_validation_writer(validate: bool) -> ValidationWriter | None` — returns a `ValidationWriter` if `validate` is True, else `None`. The handler checks for `None` before writing.

**FR-1f: Integration in `_handle_query`**
- If a `ValidationWriter` is active, call `writer.write_turn(...)` immediately after the `result` event is received from `run_agent`.
- Writing must not block the Gradio response — wrap the write in a `try/except` that logs a warning to stderr if it fails, but does not propagate the exception to the UI.
- The turn counter increments monotonically per session, not per page load.

---

### FR-2: Error Handling

**FR-2a: Unrecognised location**
- When the geocoder returns no result, the agent returns a response containing the text `"I could not locate [input] in Missouri"` rather than an empty figure panel or a traceback.
- The chatbot displays this message; the figure panel is unchanged from the previous turn.

**FR-2b: No data for requested DOY / moisture**
- When the filtered DataFrame is empty for the resolved site + DOY + moisture combination, the plot tool returns a descriptive error string instead of raising. The agent incorporates this into its plain-language response.

**FR-2c: LLM API timeout**
- `run_agent` enforces a per-call timeout (configurable via `YIELD_LLM_TIMEOUT` env var, default 60 s). On timeout, `AgentError` is raised with a human-readable message; the chatbot displays it.

---

### FR-3: Rate Limiting and Cost Guardrails

**FR-3a: Per-session token cap**
- `YIELD_MAX_SESSION_TOKENS` env var (default `50000`). If `response.usage.total_tokens` (accumulated across turns in a session) exceeds this cap, `_handle_query` returns an error message without calling `run_agent`.

**FR-3b: Daily spend cap**
- `YIELD_MAX_DAILY_USD` env var (default `5.0`). A lightweight spend tracker (`src/app/spend.py`) reads/writes a JSON file at `YIELD_SPEND_FILE` (default `./spend.json`) keyed by UTC date. If the accumulated cost for today exceeds the cap, the query is rejected with a user-visible message.
- Cost is estimated from token counts using a fixed rate table in `spend.py`; the rate table is updated manually when provider pricing changes.

---

### FR-4: Structured Operational Logging

**FR-4a: Log format**
- Each completed agent turn emits one JSON line to stdout: `{"ts": <ISO8601>, "query": <str>, "site": <str|null>, "plot_types": [<str>], "model": <str>, "latency_s": <float>, "input_tokens": <int>, "output_tokens": <int>}`.
- Written by `_handle_query` after the `result` event, using `print(json.dumps(...))`. No logging framework dependency.

**FR-4b: Validation mode flag in log**
- When validation mode is active, the log line includes `"validate": true` and `"validate_dir": <str>`.

---

### FR-5: Deployment

**FR-5a: Dockerfile (already scaffolded in Phase 3)**
- No changes required beyond verifying it builds with the packages added in Phase 5 (`spend.py` has no new dependencies).
- `YIELD_VALIDATE_DIR` should be mountable as a Docker volume for persistence.

**FR-5b: README deployment section**
- Instructions for local Docker run and VM hosting (DigitalOcean / AWS Lightsail).
- Example `docker run` command showing how to mount `YIELD_VALIDATE_DIR` and set `YIELD_MAX_DAILY_USD`.
- Optional: nginx reverse proxy snippet for TLS termination and HTTP Basic Auth.

---

## Non-Functional Requirements

- `src/app/validation.py` must be importable with no side effects and no Gradio dependency.
- `ValidationWriter.write_turn` must complete in under 500 ms for typical figure sizes (< 5 MB HTML). If it takes longer, it indicates a Plotly serialisation issue, not a design problem.
- The session index HTML must render correctly in Chrome, Firefox, and Safari when opened via `file://` — no server required.
- Validation mode must not change agent behaviour, model selection, or response content in any way.

---

## Module Interface Contract

```python
# src/app/validation.py
from pathlib import Path
import plotly.graph_objects as go

class ValidationWriter:
    def __init__(self, session_dir: Path) -> None: ...
    def write_turn(
        self,
        turn: int,
        query: str,
        response_text: str,
        raw_messages: list[dict],
        site: str | None,
        model: str,
        figures: dict[str, go.Figure],
    ) -> None: ...

def make_validation_writer(validate: bool, root: Path | None = None) -> ValidationWriter | None: ...


# src/app/spend.py
from pathlib import Path

def record_and_check(
    input_tokens: int,
    output_tokens: int,
    model: str,
    spend_file: Path,
    daily_cap_usd: float,
) -> tuple[float, bool]:
    """Returns (cost_usd, over_cap)."""
    ...
```
