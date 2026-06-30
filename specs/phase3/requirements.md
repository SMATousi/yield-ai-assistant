# Phase 3 — GUI: Requirements

## Functional Requirements

### FR-1: Startup Initialisation (`src/app/app.py`)

- When the Python process starts, load the aggregate dataset via `load_dataset(AGGREGATE_CSV)`, build the grid via `build_grid(dataset)`, and construct a `ToolContext(dataset=ds, grid=grid)`. These three objects are module-level singletons — constructed once and reused across all queries in the session.
- If `AGGREGATE_CSV` does not exist, the app raises `FileNotFoundError` before launching Gradio. The user sees the error in the terminal, not an empty UI.
- The startup path must not call the LLM or make network requests beyond what the geocoder does on first query.

---

### FR-2: Settings Sidebar (`src/app/app.py`)

The left column of the `gr.Blocks` layout is a collapsible settings panel. It contains the following controls, each with the stated behaviour.

**FR-2a: LLM Provider radio**
- `gr.Radio`, label `"LLM provider"`, choices `["Ollama (local)", "Claude API", "OpenAI", "Custom"]`, default `"Ollama (local)"`.
- Changing the selection shows/hides the provider-specific controls below it.

**FR-2b: Ollama model dropdown**
- `gr.Dropdown`, label `"Ollama model"`, visible when provider is `"Ollama (local)"`.
- Populated at app startup by `list_ollama_models()` from `state.py`. If Ollama is not running, the dropdown shows an empty list without crashing.
- A `gr.Button` labelled `"Refresh models"` re-calls `list_ollama_models()` and updates the dropdown choices. Clicking it while Ollama is unavailable silently leaves the list empty.
- The resulting model string passed to `run_agent` is `f"ollama/{selected_name}"`.

**FR-2c: Cloud model dropdown**
- `gr.Dropdown`, label `"Model"`, visible when provider is `"Claude API"` or `"OpenAI"`.
- Choices populated from `KNOWN_CLOUD_MODELS` in `state.py`:
  ```
  anthropic/claude-sonnet-4-6
  anthropic/claude-haiku-4-5-20251001
  anthropic/claude-opus-4-8
  openai/gpt-4o
  openai/gpt-4o-mini
  ```
- The selected string is passed directly to `run_agent` as `model`.

**FR-2d: API key input**
- `gr.Textbox`, label `"API key"`, `type="password"`, visible when provider is `"Claude API"` or `"OpenAI"`.
- Value written to the environment variable `ANTHROPIC_API_KEY` (for Claude) or `OPENAI_API_KEY` (for OpenAI) inside the query handler, immediately before calling `run_agent`. This approach lets LiteLLM pick it up without requiring a process restart.
- Decision: write to environment rather than pass to LiteLLM directly, because LiteLLM reads `os.environ` on every call and there is no per-call key parameter in the current interface.

**FR-2e: Custom model text field**
- `gr.Textbox`, label `"Custom model string"`, placeholder `"ollama/llama3.1:8b"`, visible when provider is `"Custom"`.
- Value passed directly to `run_agent` as `model`. No validation beyond non-empty check.

**FR-2f: Plot defaults accordion**
- Wrapped in `gr.Accordion("Plot defaults", open=False)`.
- `gr.Dropdown`, label `"Default planting date"`, choices populated at app startup from `sorted(ds.df.index.get_level_values("plt_dtDoy").unique(), key=doy_sort_key)` — all dates present in the dataset, in chronological order. Default `"Apr-15"`.
- `gr.Dropdown`, label `"Default moisture scenario"`, choices `["dry", "all", "wet"]`, default `"all"`.
- `gr.Slider`, label `"Top N treatments"`, min `1`, max `10`, step `1`, default `3`.
- These values are passed to the query handler and injected into the prompt context when the user does not explicitly specify them in their query.

---

### FR-3: Chat Interface (`src/app/app.py`)

- `gr.Chatbot`, `type="messages"`, `height=450`, `show_label=False`. Renders the full multi-turn conversation. Each assistant turn shows the text response; figures appear in the figure panel below (not inside the chatbot).
- `gr.Textbox` for query input: `show_label=False`, `placeholder="Ask about your farm (e.g. 'Best management for Audrain County in a dry spring')"`, `lines=2`, `scale=5`.
- `gr.Button("Send", variant="primary", scale=1)` — submits the query. Clicking it or pressing Shift+Enter in the textbox both trigger the query handler.
- `gr.Button("Clear")` — resets the chatbot history, clears the figure panel, clears the site label, and resets `gr.State` to a fresh `SessionState`.

**FR-3a: Query handler (`_handle_query`)**
- Signature: `_handle_query(query, chat_history, messages, model_str, default_date, default_moisture, top_n, api_key, provider) -> tuple`.
- Prepends a context hint to the raw user query if defaults differ from the model's expected inference: `f"{query} [default planting date: {default_date}, moisture: {default_moisture}, top_n: {top_n}]"`. This hint only applies when none of those terms already appear in the raw query string.
- Calls `run_agent(augmented_query, _ctx, model=model_str)`.
- Appends `{"role": "user", "content": query}` and `{"role": "assistant", "content": response.text}` to `chat_history`.
- Returns `(updated_chat_history, updated_messages, response.figure, site_label_text, html_path, query_cleared)`.
- If `run_agent` raises `AgentError` or any unhandled exception, appends an error message to `chat_history` and returns `None` for the figure and download path. Does not crash the Gradio process.
- `html_path`: if `response.figure` is not None, writes the figure to a temp file using `tempfile.NamedTemporaryFile(suffix=".html", delete=False)` and returns the path. Otherwise returns `None`.

---

### FR-4: Figure Display and Download (`src/app/app.py`)

- A `gr.Tabs` component with two tabs: **"Planting Date Response"** and **"Recommendation"**.
- Each tab contains a `gr.Plot` (show_label=False) and a `gr.DownloadButton(label="Download (HTML)", visible=False)`.
- The "Planting Date Response" tab renders the figure from `generate_doy_response_plot` (keyed as `"generate_doy_response_plot"` in `AgentResponse.figures`).
- The "Recommendation" tab renders the figure from `generate_recommendation_plot` (keyed as `"generate_recommendation_plot"`).
- Each plot is updated independently after each query. Tabs without a new figure in a given turn pass `None`, leaving the last plot in place.
- Each download button becomes visible (with the temp HTML path as its value) when its figure is available, and is hidden again after "Clear". The `_figure_download_update(figure)` helper handles both cases: returns `gr.update(visible=True, value=path)` when a figure is provided, `gr.update(visible=False)` otherwise.

---

### FR-5: Status Bar (`src/app/app.py`)

- A `gr.Markdown` component at the bottom of the main column shows two fields:
  - Resolved site: `"Site: 39.419701_-92.425003"` or `"Site: —"` if no query has resolved a site yet.
  - Active model: `"Model: ollama/qwen2.5:14b"` (updated from the settings panel whenever it changes).
- Updated by the query handler with each response.

---

### FR-6: Session State (`src/app/state.py`)

**FR-6a: `SessionState` dataclass**
- Fields: `messages: list[dict]` (LiteLLM message-format history for multi-turn agent context), `chat_history: list[dict]` (Gradio chatbot history), `last_site: str | None`.
- No `go.Figure` field — figures are not stored in state because `gr.State` must hold JSON-serialisable values.

**FR-6b: `make_session_state() -> SessionState`**
- Returns a fresh `SessionState(messages=[], chat_history=[], last_site=None)`.
- Called when the app initialises and when the user clicks "Clear".

**FR-6c: `clear_session(state: SessionState) -> SessionState`**
- Returns `make_session_state()` — a new blank state. Does not mutate the argument.

---

### FR-7: Ollama Discovery (`src/app/state.py`)

**FR-7a: `list_ollama_models(base_url: str = "http://localhost:11434") -> list[str]`**
- Issues `GET {base_url}/api/tags` with a 3-second timeout.
- On success: parses the JSON response, returns `[m["name"] for m in data.get("models", [])]` sorted alphabetically.
- On any exception (connection refused, timeout, JSON parse error): returns `[]`.
- Never raises; always returns a list.

**FR-7b: `KNOWN_CLOUD_MODELS: list[str]`**
- Module-level constant listing the cloud models shown in FR-2c.

**FR-7c: `doy_sort_key(plt_dtDoy: str) -> datetime`**
- `datetime.strptime(plt_dtDoy, "%b-%d").replace(year=2000)` — used to sort planting dates chronologically for the defaults dropdown.
- Identical logic to Phase 1's `doy_response.py`; duplicated here to avoid a cross-layer import dependency.

---

### FR-8: Dockerfile

- Base image: `python:3.11-slim`.
- Decision: use pip, not conda, inside the container — conda adds >1 GB to the image and the `environment.yml` packages are all pip-installable. The container does not need Ollama (Ollama runs on the host and is accessed via `host.docker.internal:11434`).
- Installs only the packages needed at runtime (not `pytest`, not `conda`). Add a `requirements-app.txt` in the project root listing: `pandas scipy geopy plotly gradio litellm anthropic openai requests`.
- Exposes port 7860.
- `CMD`: `python src/app/app.py`.
- `YIELD_DATA_DIR` environment variable must be set at `docker run` time (e.g. `-e YIELD_DATA_DIR=/data -v /host/data:/data`).

---

---

### FR-9: Validation Mode UI Controls (reserved for Phase 5)

The settings sidebar reserves space for the validation mode indicator introduced in Phase 5. No logic is implemented in Phase 3; the controls are wired in Phase 5.

- A `gr.Textbox` (read-only, `interactive=False`) labelled `"Saving to"` will be shown at the top of the sidebar when the app is launched with `--validate`. It displays the absolute path of the active `ValidationWriter` session directory.
- This control is hidden by default and shown only when `--validate` is active; its presence here is noted so Phase 3 layout code does not need to be reorganised in Phase 5.

---

## Non-Functional Requirements

- `src/app/app.py` and `src/app/state.py` must be importable with no side effects. The Gradio app is only built when `build_app()` is called explicitly; no UI is created at import time.
- The query handler must not crash the Gradio process for any user input. All `run_agent` exceptions are caught and displayed as error messages in the chatbot.
- `list_ollama_models()` must never raise; it returns an empty list on any failure.
- The settings sidebar visibility logic (FR-2) must be implemented purely via Gradio `.change()` event handlers — no JavaScript.
- The app must launch correctly when Ollama is not running (just shows an empty Ollama model list).
- The app must launch correctly when `ANTHROPIC_API_KEY` is not set (user sees the API key field and must fill it before a Claude query will succeed).

---

## Module Interface Contract

```python
# src/app/state.py
import dataclasses
from datetime import datetime

KNOWN_CLOUD_MODELS: list[str]

@dataclasses.dataclass
class SessionState:
    messages: list[dict]
    chat_history: list[dict]
    last_site: str | None

def make_session_state() -> SessionState: ...
def clear_session(state: SessionState) -> SessionState: ...
def list_ollama_models(base_url: str = "http://localhost:11434") -> list[str]: ...
def doy_sort_key(plt_dtDoy: str) -> datetime: ...


# src/app/app.py
import gradio as gr

def build_app() -> gr.Blocks: ...

if __name__ == "__main__":
    build_app().launch(server_name="0.0.0.0", server_port=7860)
```
