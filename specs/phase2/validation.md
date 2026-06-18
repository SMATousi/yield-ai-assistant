# Phase 2 — Agent Core: Validation

## Gate Criterion (from Roadmap)

> The agent correctly identifies the moisture scenario from natural language ("dry spring", "wet year", "average conditions"), resolves the location, and produces a plot without manual intervention.

This is the single pass/fail gate. All checklist items below must be green before Phase 3 begins.

---

## Checklist

### pytest.ini

- [x] `pytest.ini` has a `llm` marker entry: `llm: tests that require a running LLM`.
- [x] `addopts` in `pytest.ini` reads `-m "not network and not llm"` so LLM tests are deselected by default.

### tools.py — dataclasses and TOOLS list

- [x] `from src.agent.tools import ToolContext, ToolResult, TOOLS, execute_tool` imports without error and without any LLM calls, network calls, or file I/O.
- [x] `ToolContext(dataset=ds, grid=grid)` stores `.dataset` and `.grid` attributes.
- [x] `TOOLS` is a `list` with exactly 3 entries.
- [x] Each entry in `TOOLS` has keys `"type"` (== `"function"`) and `"function"`, with `"function"` containing `"name"`, `"description"`, `"parameters"`.
- [x] `TOOLS[0]["function"]["name"] == "lookup_nearest_site"`.
- [x] `TOOLS[1]["function"]["name"] == "generate_recommendation_plot"`.
- [x] `TOOLS[2]["function"]["name"] == "generate_doy_response_plot"`.
- [x] `"moisture_scenario"` in `TOOLS[1]["function"]["parameters"]["properties"]` and its `description` contains the strings `"dry"`, `"all"`, and `"wet"`.
- [x] `"planting_date"` in `TOOLS[1]["function"]["parameters"]["properties"]` and is NOT listed in `"required"` (it is optional with a default).

### tools.py — execute_tool (offline unit tests)

- [x] `execute_tool("lookup_nearest_site", {"location": "Columbia, MO"}, ctx)` returns a `ToolResult` with `figure is None` and `content` parseable as JSON containing the key `"site"`. (Test uses monkeypatched geocoder returning a fixed lat/lon.)
- [x] `execute_tool("generate_recommendation_plot", {"location": "...", "planting_date": "Apr-15", "moisture_scenario": "dry"}, ctx)` returns a `ToolResult` with `figure` as `go.Figure` and `content` parseable as JSON containing `"site"` and `"top_trt_label"`. (Test uses synthetic dataset and monkeypatched geocoder.)
- [x] `execute_tool("generate_doy_response_plot", {"location": "..."}, ctx)` returns a `ToolResult` with `figure` as `go.Figure`. (Same synthetic setup.)
- [x] `execute_tool("nonexistent_tool", {}, ctx)` raises `AgentError`.
- [x] When the geocoder raises `GeocodingError` (monkeypatched), `execute_tool` for any tool returns a `ToolResult` with non-empty `content` string and `figure is None` — no exception propagates.

### agent.py — imports and structure

- [x] `from src.agent.agent import run_agent, AgentResponse, AgentError, SYSTEM_PROMPT` imports without error.
- [x] `SYSTEM_PROMPT` is a non-empty string containing the substring `"MU Extension"`.
- [x] `AgentResponse` has fields `text`, `figure`, `site`, `raw_messages`.
- [x] `AgentError` is a subclass of `Exception`.

### interpreter.py — offline unit tests

- [x] `from src.agent.interpreter import build_interpretation_prompt, interpret` imports without error.
- [x] `build_interpretation_prompt(synthetic_df, site, plt_dtDoy, moisture_group)` returns a string containing `"P(best)"`, `"CVaR"`, and `"grid point"`. (Uses synthetic DataFrame, no LLM call.)
- [x] `build_interpretation_prompt(...)` returns a string containing the `trt_label` of the top-composite treatment in the synthetic data.
- [x] `build_interpretation_prompt(df, "nonexistent_site", "Apr-15", "dry")` raises `ValueError`.
- [x] The prompt string returned by `build_interpretation_prompt` contains the instruction substring `"≥150 words"`.

### Integration test (`@pytest.mark.llm`)

- [ ] `run_agent("Best management for Audrain County in a dry spring", ctx)` returns an `AgentResponse` where:
  - `response.figure` is a `go.Figure` instance.
  - `response.site` is not `None` and is a string matching the `"lat_lon"` format (e.g. `"39.xxx_-9x.xxx"`).
  - `len(response.text) >= 150`.
- [ ] `run_agent("Show planting date response curves for Boone County", ctx)` returns an `AgentResponse` with `figure` as a `go.Figure`.
- [ ] `run_agent("What is the best management for average conditions in Mexico, MO", ctx)` correctly uses `moisture_scenario="all"` (verifiable from `raw_messages` in the response).

### Smoke script

- [ ] `python scripts/smoke_phase2.py` runs to completion and prints `"Phase 2 OK."`.
- [ ] `smoke_agent_recommendation.html` is saved in the project root.
- [ ] The printed output shows a resolved `site` string and `text` length ≥ 150.

---

## Offline results (recorded 2026-06-17)

```
conda run -n yield-ai pytest tests/test_agent.py -v
18 passed in 2.61s
```

Full suite: 48 passed, 5 deselected (network tests).

## How to Run Validation

```bash
# Unit tests only (offline, no LLM, no network)
conda run -n yield-ai pytest tests/test_agent.py -v

# Unit + LLM integration tests (requires Ollama running with qwen2.5:14b)
conda run -n yield-ai pytest tests/test_agent.py -v -m "llm or not llm"

# Or with a Claude API key:
YIELD_LLM_MODEL=anthropic/claude-sonnet-4-6 \
conda run -n yield-ai pytest tests/test_agent.py -v -m "llm or not llm"

# Smoke test (requires LLM; saves HTML)
conda run -n yield-ai python scripts/smoke_phase2.py

# Open saved figure
open smoke_agent_recommendation.html
```
