# Phase 3 — GUI: Implementation Plan

## Overview

Build the Gradio `Blocks` application that connects the Phase 2 agent to a chat-style web interface. This phase produces two modules (`src/app/state.py`, `src/app/app.py`), a `Dockerfile`, and a `requirements-app.txt`. It does not modify any Phase 0–2 code; those modules are consumed read-only. The GUI wraps `run_agent` from `src/agent/agent.py` and the startup objects (`SummaryDataset`, `KDTreeGrid`, `ToolContext`) exactly as the Phase 2 smoke script does, but with a persistent Gradio process instead of a one-shot script.

The defining characteristic of this phase beyond the roadmap baseline is the settings sidebar: the user can select any Ollama model currently loaded on the local server (discovered via live API query), or switch to any cloud provider (Claude, OpenAI) by entering an API key. Every agent-relevant parameter — model, planting date default, moisture default, top-N — is exposed as a UI control rather than being hardcoded.

---

## Step 1: Scaffolding

```
src/app/
  __init__.py
  state.py
  app.py
requirements-app.txt     # pip deps for Docker
Dockerfile
scripts/
  smoke_phase3.py         # headless launch smoke test
```

No new conda packages needed — `gradio` and `requests` are already in `environment.yml`.

---

## Step 2: `src/app/state.py`

This module has no Gradio imports and no side effects at import time. It is a pure-Python utility layer.

### 2a. `SessionState` dataclass

```python
@dataclasses.dataclass
class SessionState:
    messages: list[dict]      # LiteLLM/OpenAI message format, for run_agent multi-turn
    chat_history: list[dict]  # Gradio chatbot format: [{"role": ..., "content": ...}]
    last_site: str | None
```

`go.Figure` is intentionally excluded — Gradio serialises `gr.State` objects and Plotly figures are not JSON-serialisable.

### 2b. `make_session_state` and `clear_session`

Both return a new `SessionState` with empty lists and `None`. `clear_session` is a thin wrapper to make call sites readable.

### 2c. `list_ollama_models`

```python
def list_ollama_models(base_url: str = "http://localhost:11434") -> list[str]:
    try:
        resp = requests.get(f"{base_url}/api/tags", timeout=3)
        resp.raise_for_status()
        return sorted(m["name"] for m in resp.json().get("models", []))
    except Exception:
        return []
```

The 3-second timeout prevents hanging if the Ollama port is open but unresponsive. Returning `[]` on any failure is intentional — the dropdown just shows empty, the app does not crash.

### 2d. `KNOWN_CLOUD_MODELS` and `doy_sort_key`

`KNOWN_CLOUD_MODELS` is a module-level list. `doy_sort_key` duplicates the same function from `src/plots/doy_response.py` — the duplication is deliberate to avoid importing a plot-layer module inside the app layer.

---

## Step 3: `src/app/app.py` — startup and layout skeleton

### 3a. Module-level singletons (startup side effects)

```python
from config import AGGREGATE_CSV, LLM_MODEL
from src.data.loader import load_dataset
from src.data.grid import build_grid
from src.agent.tools import ToolContext

_ds = load_dataset(AGGREGATE_CSV)
_grid = build_grid(_ds)
_ctx = ToolContext(dataset=_ds, grid=_grid)

_DATE_CHOICES = sorted(
    _ds.df.index.get_level_values("plt_dtDoy").unique(),
    key=doy_sort_key,
)
```

These run when the module is imported. Any `FileNotFoundError` here aborts the process before Gradio starts — that is the intended behaviour (fail fast, not silently).

Decision: module-level singletons rather than initialising inside `build_app()`. This keeps `build_app()` a pure layout function and makes the singletons available for unit tests that need to verify the app builds without error.

### 3b. `build_app() -> gr.Blocks`

Entire layout is inside this function. Nothing Gradio-related is at module level.

Layout structure (two-column `gr.Row`):

```
gr.Blocks(title="Yield AI Assistant", theme=gr.themes.Soft())
└── gr.Row()
    ├── gr.Column(scale=1, min_width=280)   ← settings sidebar
    │   ├── gr.Markdown("## Settings")
    │   ├── provider_radio      (FR-2a)
    │   ├── ollama_dd           (FR-2b)
    │   ├── refresh_btn
    │   ├── cloud_dd            (FR-2c)
    │   ├── api_key_box         (FR-2d)
    │   ├── custom_model_box    (FR-2e)
    │   └── gr.Accordion("Plot defaults")
    │       ├── default_date_dd (FR-2f)
    │       ├── default_moisture_dd
    │       └── top_n_slider
    └── gr.Column(scale=3)                  ← main area
        ├── chatbot             (FR-3)
        ├── gr.Row()
        │   ├── query_box
        │   └── send_btn
        ├── figure_display      (gr.Plot, FR-4)
        ├── download_btn        (gr.DownloadButton, FR-4)
        ├── status_md           (gr.Markdown, FR-5)
        └── clear_btn           (FR-3)
```

### 3c. Provider visibility wiring

Four `.change()` handlers on `provider_radio`, each calling `_update_provider_visibility(provider)`:

```python
def _update_provider_visibility(provider: str):
    is_ollama = provider == "Ollama (local)"
    is_cloud  = provider in ("Claude API", "OpenAI")
    is_custom = provider == "Custom"
    return (
        gr.update(visible=is_ollama),   # ollama_dd
        gr.update(visible=is_ollama),   # refresh_btn
        gr.update(visible=is_cloud),    # cloud_dd
        gr.update(visible=is_cloud),    # api_key_box
        gr.update(visible=is_custom),   # custom_model_box
    )
```

---

## Step 4: `src/app/app.py` — event handlers

### 4a. `_resolve_model_str`

```python
def _resolve_model_str(
    provider: str,
    ollama_model: str | None,
    cloud_model: str | None,
    custom_model: str | None,
) -> str:
    if provider == "Ollama (local)":
        name = (ollama_model or "").strip()
        return f"ollama/{name}" if name else LLM_MODEL
    elif provider in ("Claude API", "OpenAI"):
        return (cloud_model or LLM_MODEL).strip()
    else:
        return (custom_model or LLM_MODEL).strip()
```

### 4b. `_handle_query`

Called by both the Send button and the query textbox submit. Full signature:

```python
def _handle_query(
    query: str,
    state: SessionState,
    provider: str,
    ollama_model: str | None,
    cloud_model: str | None,
    custom_model: str | None,
    api_key: str,
    default_date: str,
    default_moisture: str,
    top_n: int,
) -> tuple[SessionState, list[dict], go.Figure | None, str, str | None, gr.update]:
```

Steps:
1. Return early (no update) if `query.strip()` is empty.
2. Set `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` in `os.environ` from `api_key` if non-empty and provider is Claude/OpenAI.
3. Call `_resolve_model_str(...)` to get the model string.
4. Build `augmented_query`:
   - If none of `default_date`, `default_moisture`, `"top"` / `"top_n"` appear in the lowercased query, append `f" [defaults: planting {default_date}, moisture {default_moisture}, show top {top_n}]"`.
5. Build the per-turn messages by prepending the current `state.messages` with the system prompt if not already present, then appending the user message. Pass this full list as the starting point for `run_agent` by setting `_ctx` and calling `run_agent(augmented_query, _ctx, model=model_str)`.

   Implementation note: `run_agent` builds its own messages list from scratch each call (it starts with `[system, user]`). For multi-turn context, pass the accumulated `state.messages` (excluding the system message) as prior context. Decision: modify the call to `run_agent` by pre-seeding its messages: inject `state.messages` as prior turns between the system prompt and the new user message. This requires a small wrapper or a new optional parameter to `run_agent`. For Phase 3, implement a wrapper that prepends history:

   ```python
   def _run_with_history(query: str, history: list[dict], model: str) -> AgentResponse:
       # history is the accumulated messages list from previous turns
       # We inject it between system and new user message
       ...
   ```

   This is the only Phase 3 touch to the agent layer: add an optional `prior_messages: list[dict] | None = None` parameter to `run_agent` in `agent.py`. When provided, these messages are inserted between the system prompt and the current user message.

6. On success: append `{"role": "user", "content": query}` and `{"role": "assistant", "content": response.text}` to `state.chat_history`. Save `response.raw_messages` (excluding the system message) to `state.messages` for next-turn context. Update `state.last_site`.
7. On exception: append error message to `state.chat_history`; return `None` for figure/download.
8. If `response.figure` is not None: write to `tempfile.NamedTemporaryFile(suffix=".html", delete=False, dir="/tmp")` and return the path for the download button.
9. Returns:
   - `state` (updated `SessionState`)
   - `state.chat_history` (for `chatbot` update)
   - `response.figure` (for `figure_display` update)
   - `f"Site: {response.site or '—'}  |  Model: {model_str}"` (for `status_md`)
   - `html_path` (for `download_btn` value)
   - `gr.update(value="")` (clears the query textbox)

### 4c. `_refresh_ollama_models`

```python
def _refresh_ollama_models() -> gr.update:
    return gr.update(choices=list_ollama_models())
```

### 4d. `_clear_session`

```python
def _clear_session() -> tuple[SessionState, list, None, str, None, gr.update]:
    return (
        make_session_state(),
        [],           # chatbot
        None,         # figure_display
        "Site: —",    # status_md
        None,         # download_btn value
        gr.update(visible=False),  # download_btn visibility
    )
```

---

## Step 5: `agent.py` — add `prior_messages` parameter

Add `prior_messages: list[dict] | None = None` to `run_agent`. When provided and non-empty, insert the list between the system message and the new user message:

```python
messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
if prior_messages:
    messages.extend(prior_messages)
messages.append({"role": "user", "content": user_query})
```

This is the only modification to Phase 2 code in this phase.

---

## Step 6: `requirements-app.txt` and `Dockerfile`

### `requirements-app.txt`

```
pandas>=2.0
scipy
geopy
plotly>=5.20
gradio>=4.0
litellm
anthropic
openai
requests
numpy
```

### `Dockerfile`

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements-app.txt .
RUN pip install --no-cache-dir -r requirements-app.txt

COPY config.py .
COPY src/ src/

EXPOSE 7860
ENV YIELD_DATA_DIR=/data

CMD ["python", "src/app/app.py"]
```

Build: `docker build -t yield-ai .`
Run: `docker run -p 7860:7860 -e YIELD_LLM_MODEL=anthropic/claude-sonnet-4-6 -e ANTHROPIC_API_KEY=sk-... -v /path/to/data:/data yield-ai`

Decision: Python slim base image rather than Miniconda. The image is ~500 MB smaller and builds in ~60 seconds vs ~5 minutes for conda. The conda environment is for local development only; pip is sufficient inside the container.

---

## Step 7: Smoke script (`scripts/smoke_phase3.py`)

Headless test — does not open a browser, just verifies the app builds without error and the startup singletons load:

```python
import gradio as gr
from src.app.app import build_app, _ds, _ctx

assert len(_ds.sites) > 0
app = build_app()
assert isinstance(app, gr.Blocks)
print(f"App built. {len(_ds.sites)} sites, {len(_ds.df):,} rows.")
print("Phase 3 OK.")
```

No LLM call, no network call, no browser.

---

## Sequence Diagram

```
user types query + clicks Send
  │
  ▼
_handle_query(query, state, provider, ollama_model, ..., default_date, ...)
  │
  ├─ _resolve_model_str(provider, ...) ──► model_str (e.g. "ollama/qwen2.5:14b")
  │
  ├─ set os.environ[API_KEY] if needed
  │
  ├─ augment query with defaults hint if not already in query
  │
  ├─ run_agent(augmented_query, _ctx, model=model_str,
  │            prior_messages=state.messages)
  │     │
  │     ├─ [Phase 2 agent loop]
  │     │    litellm.completion → tool calls → execute_tool → plot figures
  │     │    interpret() → explanation text
  │     └─ AgentResponse(text, figure, site, raw_messages)
  │
  ├─ figure.write_html(tmp_path) if figure is not None
  │
  ├─ update state.chat_history, state.messages, state.last_site
  │
  └─ return (state, chat_history, figure, status_text, tmp_path, clear_query)
              │         │           │         │            │
              ▼         ▼           ▼         ▼            ▼
           gr.State  gr.Chatbot  gr.Plot  gr.Markdown  gr.DownloadButton
```

```
user changes provider radio → "Claude API"
  │
  ▼
_update_provider_visibility("Claude API")
  ├─ ollama_dd.visible = False
  ├─ refresh_btn.visible = False
  ├─ cloud_dd.visible = True
  ├─ api_key_box.visible = True
  └─ custom_model_box.visible = False
```
