# Phase 2 — Agent Core: Requirements

## Functional Requirements

### FR-1: Tool Definitions (`src/agent/tools.py`)

Define the three tools the LLM can call, their Python executor functions, and the shared context object that bridges the agent to Phase 0 and Phase 1 infrastructure.

**FR-1a: `ToolContext` dataclass**
- Holds references to the live Phase 0 objects: `dataset: SummaryDataset` and `grid: KDTreeGrid`.
- Passed into every tool executor so tools never import globals — all data access goes through this context.
- Constructed once at application startup (in `agent.py` or the app layer) and reused across queries.

**FR-1b: `ToolResult` dataclass**
- Fields: `content: str` (JSON-serialisable summary string sent back to the LLM as the tool result), `figure: go.Figure | None` (populated when a plot was generated; `None` for `lookup_nearest_site`).
- `content` must be plain text or a JSON string — never a binary object.

**FR-1c: `TOOLS` list**
- A module-level `list[dict]` in OpenAI function-calling format (LiteLLM's `tools=` parameter).
- Three entries, one per tool:
  1. `lookup_nearest_site` — resolves a free-text location to the nearest grid site string and returns the site key, its coordinates, and the distance from the query point. Description instructs the LLM: "Call this first whenever the user mentions a location to confirm which grid point will be used."
  2. `generate_recommendation_plot` — generates the two-panel recommendation figure for a given location, planting date, and moisture scenario. The `moisture_scenario` parameter is a string enum `["dry", "all", "wet"]`; the description maps natural language: `"dry spring"`, `"drought year"` → `"dry"`; `"wet year"`, `"above-average precipitation"` → `"wet"`; `"average"`, `"normal"`, `"all conditions"` → `"all"`. The `planting_date` parameter is in `"Mon-DD"` format (e.g. `"Apr-15"`); it is optional and defaults to `"Apr-15"` if the user does not specify one.
  3. `generate_doy_response_plot` — generates the three-panel planting-date response figure for a location, showing all moisture groups.

**FR-1d: `execute_tool(name, arguments, ctx) -> ToolResult`**
- Dispatches on `name` to the corresponding private implementation function.
- Raises `AgentError` if `name` is not recognised.
- Each implementation function:
  - `_lookup_nearest_site(location: str, ctx: ToolContext) -> ToolResult`: calls `geocode(location)` then `ctx.grid.nearest_site(lat, lon)`; `content` = JSON with keys `site`, `lat`, `lon`, `distance_deg`.
  - `_generate_recommendation_plot(location: str, planting_date: str, moisture_scenario: str, ctx: ToolContext) -> ToolResult`: resolves site, calls `plot_recommendation(ctx.dataset.df, site, planting_date, moisture_scenario)`; `content` = JSON with keys `site`, `plt_dtDoy`, `moisture_group`, `top_trt_label` (the highest-composite treatment label), `top_p_best`; `figure` = the returned `go.Figure`.
  - `_generate_doy_response_plot(location: str, ctx: ToolContext) -> ToolResult`: resolves site, calls `plot_doy_response(ctx.dataset.df, site)`; `content` = JSON with keys `site`, `date_range` (min–max planting date), `moisture_groups`; `figure` = the returned `go.Figure`.
- If geocoding raises `GeocodingError` or a plot function raises `ValueError`, catch it and return a `ToolResult` with `content` = a plain error message string and `figure = None`. Do not propagate these exceptions — the LLM needs a text result to continue.

---

### FR-2: Orchestration Loop (`src/agent/agent.py`)

**FR-2a: `AgentError` exception**
- Raised when the agent cannot continue: max iterations exceeded, or the model repeatedly returns malformed tool calls.

**FR-2b: `AgentResponse` dataclass**
- Fields: `text: str`, `figures: dict[str, go.Figure]` (all figures generated in the turn, keyed by tool name e.g. `"generate_doy_response_plot"`, `"generate_recommendation_plot"`; empty dict when no plot was produced), `site: str | None` (last resolved site, for use by the GUI), `raw_messages: list[dict]` (full message history for debugging).

**FR-2c: `SYSTEM_PROMPT` constant**
- A module-level string defined in `agent.py`.
- Instructs the model to:
  1. Always call `lookup_nearest_site` or a plot-generating tool when a location is mentioned before providing agronomic advice.
  2. Map natural-language moisture terms to `"dry"`, `"all"`, or `"wet"`.
  3. After receiving a plot tool result, provide a plain-language explanation of the top treatments.
  4. Keep responses concise and use agronomic terminology appropriate for extension field agronomists.

**FR-2d: `run_agent(user_query, ctx, max_iterations=10, model=LLM_MODEL) -> AgentResponse`**
- Builds an initial `messages` list with the system prompt and the user query.
- Calls `litellm.completion(model=model, messages=messages, tools=TOOLS)` in a loop.
- On each iteration:
  - If the response contains `tool_calls`, execute each tool call via `execute_tool`, append the assistant message and the tool result message(s) to `messages`, accumulate any non-`None` `figure` from `ToolResult` into the `figures` dict keyed by tool name, capture `site` from tool result `content` if present.
  - If the response has no `tool_calls`, break the loop. The response text becomes the base for the final answer.
- After the loop, if a figure was generated and `interpret` is available, call `interpret(ctx.dataset.df, site, plt_dtDoy, moisture_group, model)` from `interpreter.py` and append the interpretation to the response text.
- If `max_iterations` is reached without a `tool_calls`-free response, raise `AgentError("max_iterations exceeded")`.
- Return `AgentResponse(text=..., figures=..., site=..., raw_messages=messages)`.

**FR-2e: Tool call output validation**
- Before calling `execute_tool`, validate that `tool_call.function.name` is in the known tool names list. If not, append an error tool result message and continue (do not raise — give the model a chance to recover).
- Validate that `tool_call.function.arguments` is parseable as JSON. If not, append an error tool result message and continue.

---

### FR-3: Plain-Language Interpreter (`src/agent/interpreter.py`)

**FR-3a: `build_interpretation_prompt(df, site, plt_dtDoy, moisture_group) -> str`**
- Accepts the aggregate DataFrame, the resolved site string, planting date, and moisture group.
- Calls `_filter_recommendation` equivalent logic to extract the top 3 treatments by composite score for the given combination.
- Builds and returns a prompt string containing:
  - The top 3 treatment labels, their `P_best` percentages, `CVaR_20` values, and `composite` scores.
  - Explicit instructions to Claude to explain: (1) why the #1 treatment is recommended, (2) the risk-return trade-off among the top 3, and (3) any caveats about grid resolution (the nearest grid point may not exactly match the user's farm).
  - A length instruction: response must be ≥150 words and written for extension agronomists (not data scientists).
- Raises `ValueError` if the filter returns zero rows.

**FR-3b: `interpret(df, site, plt_dtDoy, moisture_group, model=LLM_MODEL) -> str`**
- Calls `build_interpretation_prompt` to get the prompt string.
- Calls `litellm.completion(model=model, messages=[{"role": "user", "content": prompt}])` — no `tools=` parameter (pure text completion).
- Returns `response.choices[0].message.content`.
- This is a stateless call — it does not share message history with the main agent loop.

---

## Non-Functional Requirements

- All three modules (`tools.py`, `agent.py`, `interpreter.py`) must be importable with no side effects at import time. No LiteLLM calls, no dataset access, no network calls occur on import.
- `run_agent` must not mutate the `ToolContext` (the `SummaryDataset` and `KDTreeGrid` are read-only at runtime).
- `execute_tool` must never raise an exception to `run_agent` for user-input errors (bad location, date not in dataset). These are caught and converted to `ToolResult.content` error strings so the LLM can inform the user gracefully.
- The agent loop must terminate in ≤10 LLM calls per query. One well-formed query should resolve in 2–3 calls: `lookup_nearest_site` → `generate_recommendation_plot` → final response.
- `AgentError` is the only exception that propagates out of `run_agent`; it is reserved for programming errors (malformed tool names, max iterations exceeded) — not for geocoding or plot failures.
- Unit tests for `tools.py` and `interpreter.py` must run offline (no LLM calls). Integration tests that call the LLM are marked `@pytest.mark.llm` and excluded from the default `addopts` run.

---

## Module Interface Contract

```python
# src/agent/tools.py
import dataclasses
import plotly.graph_objects as go
from src.data.loader import SummaryDataset
from src.data.grid import KDTreeGrid

@dataclasses.dataclass
class ToolContext:
    dataset: SummaryDataset
    grid: KDTreeGrid

@dataclasses.dataclass
class ToolResult:
    content: str           # JSON string or plain error text; sent back to LLM
    figure: go.Figure | None

TOOLS: list[dict]          # OpenAI-format tool schema list; passed to litellm.completion

def execute_tool(
    name: str,
    arguments: dict,
    ctx: ToolContext,
) -> ToolResult: ...


# src/agent/agent.py
import dataclasses
import plotly.graph_objects as go

class AgentError(Exception): ...

@dataclasses.dataclass
class AgentResponse:
    text: str
    figures: dict[str, go.Figure]  # keyed by tool name; empty dict if no plot produced
    site: str | None
    raw_messages: list[dict]

SYSTEM_PROMPT: str

def run_agent(
    user_query: str,
    ctx: "ToolContext",          # imported from tools.py
    max_iterations: int = 10,
    model: str = ...,            # defaults to config.LLM_MODEL
) -> AgentResponse: ...


# src/agent/interpreter.py
import pandas as pd

def build_interpretation_prompt(
    df: pd.DataFrame,
    site: str,
    plt_dtDoy: str,
    moisture_group: str,
) -> str: ...

def interpret(
    df: pd.DataFrame,
    site: str,
    plt_dtDoy: str,
    moisture_group: str,
    model: str = ...,            # defaults to config.LLM_MODEL
) -> str: ...
```
