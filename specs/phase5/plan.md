# Phase 5 — Hardening & Deployment: Implementation Plan

## Overview

Phase 5 adds production-readiness on top of the working Phase 3 GUI. The largest new deliverable is **validation mode** (FR-1): a recording layer that saves every query, response, and figure to disk so MU Extension agronomists can review the system's outputs before trusting it for field use. The remaining work (error handling, token caps, operational logging) is additive and does not change agent behaviour.

New files in this phase:
```
src/app/validation.py   # ValidationWriter + make_validation_writer
src/app/spend.py        # daily cost tracking
scripts/smoke_phase5.py # headless validation-mode smoke test
```

Modified files:
```
src/app/app.py          # --validate flag, banner, writer integration in _handle_query
src/agent/agent.py      # LLM timeout, token accumulation in AgentResponse
README.md               # deployment section
```

---

## Step 1: `src/app/validation.py`

### 1a. Directory structure helpers

```python
def _session_dir(root: Path) -> Path:
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    path = root / ts
    path.mkdir(parents=True, exist_ok=True)
    return path

def _turn_dir(session_dir: Path, turn: int) -> Path:
    path = session_dir / f"{turn:03d}"
    path.mkdir(exist_ok=True)
    return path
```

### 1b. `ValidationWriter.write_turn`

Steps executed in order:
1. Create `_turn_dir(session_dir, turn)`.
2. Write `query.txt`, `response.txt` (plain UTF-8).
3. Write `conversation.json` using `json.dumps(raw_messages, indent=2, default=str)` — `default=str` handles any non-serialisable values (e.g. Plotly figures accidentally left in messages) without crashing.
4. For each figure key in `{"generate_doy_response_plot": "doy_response.html", "generate_recommendation_plot": "recommendation.html"}`: if the key exists in `figures`, call `fig.write_html(turn_dir / filename)`.
5. Call `_write_index(session_dir)`.

### 1c. `_write_index`

Maintains a list of turn metadata in `session_dir / "turns.json"` (appended each turn, never rewritten from scratch to avoid read-modify-write on large sessions). Reads `turns.json`, renders the HTML table, writes `index.html`.

The index HTML is a single self-contained string (no template engine). Use an f-string with a `<style>` block inline. Table columns: `#`, `Timestamp`, `Query`, `Site`, `Model`, `DOY Plot`, `Recommendation`.

### 1d. `make_validation_writer`

```python
def make_validation_writer(validate: bool, root: Path | None = None) -> ValidationWriter | None:
    if not validate:
        return None
    effective_root = root or Path(os.getenv("YIELD_VALIDATE_DIR", "./validation_runs"))
    return ValidationWriter(session_dir=_session_dir(effective_root))
```

---

## Step 2: `src/app/spend.py`

Simple JSON file keyed by UTC date string (`"2026-06-30"`). Each entry is `{"input_tokens": int, "output_tokens": int, "cost_usd": float}`.

Rate table (update manually when pricing changes):
```python
_RATES: dict[str, tuple[float, float]] = {
    # model_prefix: (input_cost_per_1k, output_cost_per_1k)
    "anthropic/claude-sonnet": (0.003, 0.015),
    "anthropic/claude-haiku":  (0.00025, 0.00125),
    "anthropic/claude-opus":   (0.015, 0.075),
    "openai/gpt-4o":           (0.0025, 0.010),
    "openai/gpt-4o-mini":      (0.00015, 0.0006),
}
_DEFAULT_RATE = (0.0, 0.0)  # local models are free
```

`record_and_check` uses a file lock (`fcntl.flock`) to avoid race conditions under concurrent Gradio workers, then returns `(cost_usd, over_cap)`.

---

## Step 3: `app.py` — validation mode wiring

### 3a. CLI flag

```python
parser.add_argument("--validate", action="store_true")
args = parser.parse_args()
_writer = make_validation_writer(args.validate)
```

`_writer` is a module-level singleton (like `_ctx`). `build_app()` receives it as a parameter or reads it from the module level.

### 3b. UI indicator

At the top of `build_app()`, before the main `gr.Row`:

```python
if _writer is not None:
    gr.Info(f"Validation mode — saving to {_writer.session_dir}", duration=None)
    gr.Textbox(
        value=str(_writer.session_dir),
        label="Saving to",
        interactive=False,
    )
```

### 3c. `_handle_query` — write after result event

Inside the `elif event.type == "result":` block, after updating `state`:

```python
if _writer is not None:
    try:
        _writer.write_turn(
            turn=len(state.messages) // 2,  # approximate turn count
            query=query,
            response_text=response.text,
            raw_messages=response.raw_messages,
            site=state.last_site,
            model=model_str,
            figures=response.figures,
        )
    except Exception as exc:
        print(f"[validation] write failed: {exc}", file=sys.stderr)
```

### 3d. Operational log line

Also inside the `result` block, after the validation write:

```python
import json, time
print(json.dumps({
    "ts": datetime.utcnow().isoformat(),
    "query": query,
    "site": state.last_site,
    "plot_types": list(response.figures.keys()),
    "model": model_str,
    "latency_s": round(time.monotonic() - _turn_start, 2),
    "input_tokens": getattr(response, "input_tokens", None),
    "output_tokens": getattr(response, "output_tokens", None),
    **({"validate": True, "validate_dir": str(_writer.session_dir)} if _writer else {}),
}))
```

---

## Step 4: Error handling additions to `agent.py`

- Add `timeout: float = float(os.getenv("YIELD_LLM_TIMEOUT", "60"))` parameter to `run_agent`.
- Pass `timeout=timeout` to each `litellm.completion` call.
- Wrap in `try/except litellm.Timeout` → raise `AgentError("LLM timed out after {timeout}s")`.
- Add `input_tokens: int = 0` and `output_tokens: int = 0` fields to `AgentResponse`; populate from `response.usage` after each completion call.

---

## Step 5: Smoke script (`scripts/smoke_phase5.py`)

```python
import tempfile
from pathlib import Path
from src.app.validation import make_validation_writer
import plotly.graph_objects as go

with tempfile.TemporaryDirectory() as tmp:
    writer = make_validation_writer(validate=True, root=Path(tmp))
    assert writer is not None
    writer.write_turn(
        turn=1,
        query="Best management for Boone County?",
        response_text="Top treatment is 3.9_90000_15.",
        raw_messages=[{"role": "user", "content": "Best management for Boone County?"}],
        site="38.961_-92.328",
        model="test/model",
        figures={"generate_recommendation_plot": go.Figure()},
    )
    index = Path(writer.session_dir) / "index.html"
    assert index.exists(), "index.html not written"
    rec = list(Path(writer.session_dir).glob("001/recommendation.html"))
    assert rec, "recommendation.html not written"
    print("Phase 5 smoke OK.")
```

---

## Sequence: validation mode turn

```
user submits query
  │
  ▼
_handle_query(...)
  │
  ├─ run_agent(...)  [yields log / result / error events]
  │
  ├─ [on result event]
  │   ├─ update state (chat_history, messages, last_site)
  │   ├─ ValidationWriter.write_turn(...)   ← new
  │   │     ├─ write query.txt, response.txt, conversation.json
  │   │     ├─ write doy_response.html, recommendation.html
  │   │     └─ regenerate index.html
  │   ├─ print(json.dumps(operational_log_line))   ← new
  │   └─ yield Gradio updates (unchanged)
  │
  └─ [Gradio renders chatbot + figures]
```
