# Phase 3 — GUI: Validation

## Gate Criterion (from Roadmap)

> A non-technical user can go from typing a county name to seeing a recommendation plot and reading a plain-language explanation in under 10 seconds, with no error messages.

This is the single pass/fail gate. All checklist items below must be green before Phase 4 begins.

---

## Checklist

### Startup

- [x] `python src/app/app.py` starts without error when `AGGREGATE_CSV` exists; Gradio opens at `http://localhost:7860`.
- [x] `python src/app/app.py` exits with a `FileNotFoundError` and a clear message when `AGGREGATE_CSV` does not exist, before Gradio launches.
- [ ] `from src.app.app import build_app` imports without side effects (does not build or launch a UI) when the environment does not have `AGGREGATE_CSV`.

### state.py — offline unit tests

- [x] `from src.app.state import SessionState, make_session_state, clear_session, list_ollama_models, KNOWN_CLOUD_MODELS, doy_sort_key` imports without error.
- [x] `make_session_state()` returns a `SessionState` with `messages == []`, `chat_history == []`, `last_site is None`.
- [x] `clear_session(state)` returns a new `SessionState`; does not mutate the argument.
- [x] `list_ollama_models()` returns `[]` without raising when Ollama is not running (monkeypatched `requests.get` raises `ConnectionError`).
- [x] `list_ollama_models()` returns a sorted list of model name strings when `requests.get` returns a valid JSON response `{"models": [{"name": "qwen2.5:14b"}, {"name": "llama3.1:8b"}]}`.
- [x] `doy_sort_key("Apr-15")` returns a `datetime` object; `doy_sort_key("Mar-15") < doy_sort_key("Apr-15")` is True.
- [x] `KNOWN_CLOUD_MODELS` is a `list` with at least 3 entries, all containing `"/"` (provider/model format).

### app.py — structure (offline)

- [x] `from src.app.app import build_app, _ds, _ctx` imports without error when `AGGREGATE_CSV` exists.
- [x] `build_app()` returns a `gr.Blocks` instance without raising.
- [x] The returned `gr.Blocks` has a `title` of `"Yield AI Assistant"`.
- [x] `_ds.sites` is a non-empty list of site strings.
- [x] `_ctx` is a `ToolContext` with `.dataset is _ds`.

### app.py — sidebar controls

- [x] The layout contains a `gr.Radio` with choices `["Ollama (local)", "Claude API", "OpenAI", "Custom"]`.
- [x] The layout contains a `gr.Dropdown` for the Ollama model with `visible=True` when provider is `"Ollama (local)"`.
- [x] The layout contains a `gr.Dropdown` for cloud models whose choices include `"anthropic/claude-sonnet-4-6"`.
- [x] The layout contains a `gr.Textbox` with `type="password"` for the API key.
- [x] The layout contains a `gr.Accordion` labelled `"Plot defaults"` containing sliders/dropdowns for planting date, moisture scenario, and top-N.
- [x] The planting date dropdown choices are in chronological order (not alphabetical): `"Mar-15"` appears before `"Apr-01"` in the list.

### app.py — `_resolve_model_str`

- [x] `_resolve_model_str("Ollama (local)", "qwen2.5:14b", None, None)` returns `"ollama/qwen2.5:14b"`.
- [x] `_resolve_model_str("Ollama (local)", None, None, None)` returns the default `LLM_MODEL` (does not crash on None/empty).
- [x] `_resolve_model_str("Claude API", None, "anthropic/claude-sonnet-4-6", None)` returns `"anthropic/claude-sonnet-4-6"`.
- [x] `_resolve_model_str("Custom", None, None, "ollama/llama3.1:8b")` returns `"ollama/llama3.1:8b"`.

### agent.py — `prior_messages` parameter

- [x] `run_agent(query, ctx, prior_messages=[])` behaves identically to `run_agent(query, ctx)` — no regression.
- [x] `run_agent(query, ctx, prior_messages=[{"role":"user","content":"prev turn"}, {"role":"assistant","content":"prev response"}])` inserts those messages between the system prompt and the new user message (verifiable from `response.raw_messages`).

### Manual acceptance tests (require running app + LLM)

- [ ] Open `http://localhost:7860`. The page loads within 3 seconds.
- [ ] With Ollama provider selected, the model dropdown shows currently loaded Ollama models. Clicking "Refresh models" updates the list.
- [ ] Typing `"Best management for Boone County, MO in a dry spring"` and clicking Send returns a recommendation figure and explanation text within 30 seconds (or within 10 seconds on Claude API).
- [ ] The figure panel shows an interactive Plotly figure; hovering over a dot in Panel A displays the treatment label and P(best) value.
- [ ] The "Download figure (HTML)" button becomes visible after a figure is generated. Clicking it downloads a valid HTML file that opens in a browser.
- [ ] The status bar shows `"Site: 38.xxx_-9x.xxx  |  Model: ollama/qwen2.5:14b"` (or the active model) after the query resolves.
- [ ] Switching provider to `"Claude API"`, entering a valid API key, selecting `"anthropic/claude-sonnet-4-6"`, and submitting a query produces a response. The API key field value is never echoed in the chatbot or status bar.
- [ ] Clicking "Clear" resets the chatbot, removes the figure, resets the status bar to `"Site: —"`, and hides the download button.
- [ ] A second query after Clear starts a fresh conversation (no memory of the first query in the response).
- [ ] Submitting a second query in the same session (without Clear) uses the prior turn as context (multi-turn chat works).

### Smoke script

- [x] `python scripts/smoke_phase3.py` runs to completion without error and prints `"Phase 3 OK."`.
- [x] Output includes the number of sites and rows loaded.

### Dockerfile

- [ ] `docker build -t yield-ai .` completes without error.
- [ ] `docker run -p 7860:7860 -e YIELD_LLM_MODEL=... -v /path/to/data:/data yield-ai` starts the app and `http://localhost:7860` is reachable from the host.

---

## How to Run Validation

```bash
# Offline unit tests (state.py, app structure, _resolve_model_str, run_agent prior_messages)
conda run -n yield-ai pytest tests/test_app.py -v

# Smoke test (loads real CSV, builds app, no LLM)
conda run -n yield-ai python scripts/smoke_phase3.py

# Launch the app (requires Ollama or API key)
conda run -n yield-ai python src/app/app.py

# Launch with Claude API
YIELD_LLM_MODEL=anthropic/claude-sonnet-4-6 \
ANTHROPIC_API_KEY=sk-... \
conda run -n yield-ai python src/app/app.py

# Docker build and run
docker build -t yield-ai .
docker run -p 7860:7860 \
  -e YIELD_LLM_MODEL=anthropic/claude-sonnet-4-6 \
  -e ANTHROPIC_API_KEY=sk-... \
  -v "$(pwd)/data:/data" \
  yield-ai
```
