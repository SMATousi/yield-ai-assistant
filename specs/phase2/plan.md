# Phase 2 — Agent Core: Implementation Plan

## Overview

Build the LLM-powered orchestration layer that sits between user queries and the Phase 0/1 infrastructure. This phase produces three modules under `src/agent/`, a test file, a smoke script, and a new pytest marker. It does not touch the GUI (Phase 3), the RAG knowledge base (Phase 4), or any Phase 0/1 code — those modules are consumed read-only.

The agent uses LiteLLM's `tools=` parameter (OpenAI function-calling format) to let the model decide which plots to generate and for which parameters. Plot generation and geocoding remain deterministic Python — the LLM only provides reasoning and parameter extraction.

---

## Step 1: Scaffolding

Create `src/agent/` with init files and add the `llm` pytest marker:

```
src/agent/
  __init__.py
  tools.py
  agent.py
  interpreter.py
tests/
  test_agent.py      # new
scripts/
  smoke_phase2.py    # new
```

Add to `pytest.ini`:
```ini
markers =
    network: tests that make real network calls (deselect with -m "not network")
    llm: tests that require a running LLM (deselect with -m "not llm")

addopts = -m "not network and not llm"
```

No new dependencies — `litellm` is already in `environment.yml`.

---

## Step 2: `src/agent/tools.py`

### 2a. Dataclasses

```python
@dataclasses.dataclass
class ToolContext:
    dataset: SummaryDataset
    grid: KDTreeGrid

@dataclasses.dataclass
class ToolResult:
    content: str
    figure: go.Figure | None = None
```

`ToolContext` is the only way tool functions access Phase 0 objects — no module-level singletons. This makes unit testing straightforward: construct a `ToolContext` with a synthetic dataset and a mock grid.

### 2b. `TOOLS` list

Define the three tool schemas as a module-level `list[dict]`. Each entry follows the OpenAI format:

```python
{
    "type": "function",
    "function": {
        "name": "...",
        "description": "...",
        "parameters": {
            "type": "object",
            "properties": { ... },
            "required": [...]
        }
    }
}
```

Key description wording to include verbatim (so models map natural language correctly):

- `lookup_nearest_site` description: "Resolve a free-text location (county name, city, ZIP code, or address in Missouri) to the nearest grid site. Returns the site key, its coordinates, and distance from the query point. Call this first whenever the user mentions a location, before generating any plot."
- `generate_recommendation_plot` → `moisture_scenario` description: "One of: 'dry', 'all', 'wet'. Map from natural language: 'dry spring', 'drought year', 'dry conditions' → 'dry'; 'wet year', 'above-average precipitation', 'wet season' → 'wet'; 'average', 'normal', 'typical', 'all conditions' → 'all'."
- `generate_recommendation_plot` → `planting_date` description: "Planting date in 'Mon-DD' format, e.g. 'Apr-15'. If the user does not specify a date, use 'Apr-15' as the default." Mark as not required in `required` list.

### 2c. Tool executor implementations

Private functions, one per tool:

**`_lookup_nearest_site(location, ctx)`**
1. Call `geocode(location)` → `(lat, lon)`.
2. Call `ctx.grid.nearest_site(lat, lon)` → `site`.
3. Compute Euclidean distance: `distance = sqrt((lat - site_lat)^2 + (lon - site_lon)^2)`.
4. Return `ToolResult(content=json.dumps({"site": site, "lat": ..., "lon": ..., "distance_deg": round(distance, 4)}))`.

**`_generate_recommendation_plot(location, planting_date, moisture_scenario, ctx)`**
1. Resolve site via `geocode` + `ctx.grid.nearest_site`.
2. Call `plot_recommendation(ctx.dataset.df, site, planting_date, moisture_scenario)` → `fig`.
3. Extract top treatment: filter df to `(site, planting_date, moisture_scenario)`, sort by `composite` desc, take row 0, get its `trt_label`.
4. Return `ToolResult(content=json.dumps({...}), figure=fig)`.

**`_generate_doy_response_plot(location, ctx)`**
1. Resolve site.
2. Call `plot_doy_response(ctx.dataset.df, site)` → `fig`.
3. Extract `date_range` from unique `plt_dtDoy` values for that site.
4. Return `ToolResult(content=json.dumps({...}), figure=fig)`.

Error handling: wrap the entire body of each private function in `try/except (GeocodingError, ValueError) as e` → return `ToolResult(content=str(e))`. This keeps all user-input errors inside the tool result string.

### 2d. `execute_tool` dispatcher

```python
_DISPATCH = {
    "lookup_nearest_site": _lookup_nearest_site,
    "generate_recommendation_plot": _generate_recommendation_plot,
    "generate_doy_response_plot": _generate_doy_response_plot,
}

def execute_tool(name: str, arguments: dict, ctx: ToolContext) -> ToolResult:
    fn = _DISPATCH.get(name)
    if fn is None:
        raise AgentError(f"Unknown tool: {name!r}")
    return fn(**arguments, ctx=ctx)
```

---

## Step 3: `src/agent/agent.py`

### 3a. `SYSTEM_PROMPT`

Write as a multi-line string constant. Cover:
- Role: "You are an agronomic advisor assistant for MU Extension in Missouri. You help field agronomists interpret soybean management trial results."
- Tool use rules: always call a tool before giving advice; never fabricate plot data; always resolve location before generating a plot.
- Moisture mapping: repeat the same natural-language → enum mapping from the tool description for redundancy.
- Tone: "Respond in plain English at a level appropriate for an experienced field agronomist. Be concise. Avoid statistical jargon unless explaining a metric."

### 3b. Orchestration loop

```python
def run_agent(user_query, ctx, max_iterations=10, model=LLM_MODEL) -> AgentResponse:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user",   "content": user_query},
    ]
    figure = None
    site = None
    plt_dtDoy = None
    moisture_group = None

    for _ in range(max_iterations):
        response = litellm.completion(model=model, messages=messages, tools=TOOLS)
        msg = response.choices[0].message

        if not msg.tool_calls:
            break   # model gave a final answer; exit loop

        messages.append(msg.model_dump(exclude_unset=True))

        for tc in msg.tool_calls:
            # Validate name
            if tc.function.name not in _KNOWN_TOOL_NAMES:
                messages.append(_tool_error_message(tc.id, "Unknown tool name"))
                continue
            # Validate JSON
            try:
                args = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                messages.append(_tool_error_message(tc.id, "Invalid JSON in arguments"))
                continue

            result = execute_tool(tc.function.name, args, ctx)

            # Capture figure and site from result
            if result.figure is not None:
                figure = result.figure
            parsed = _try_parse_json(result.content)
            if parsed and "site" in parsed:
                site = parsed["site"]
            if parsed and "plt_dtDoy" in parsed:
                plt_dtDoy = parsed["plt_dtDoy"]
            if parsed and "moisture_group" in parsed:
                moisture_group = parsed["moisture_group"]

            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "name": tc.function.name,
                "content": result.content,
            })
    else:
        raise AgentError("max_iterations exceeded")

    base_text = msg.content or ""
    interpretation = ""
    if figure is not None and site and plt_dtDoy and moisture_group:
        try:
            interpretation = interpret(ctx.dataset.df, site, plt_dtDoy, moisture_group, model=model)
        except Exception:
            pass   # interpretation failure must not crash the agent

    text = base_text
    if interpretation:
        text = text + "\n\n---\n\n" + interpretation

    return AgentResponse(text=text, figure=figure, site=site, raw_messages=messages)
```

Key design decisions:
- **Decision: append interpretation as a separate block** (separated by `---`) rather than re-running the main loop. The interpreter makes one focused LLM call with a fully formed prompt; injecting this into the main message history would add latency and complexity.
- **Decision: swallow interpreter exceptions** — if `interpret()` fails (model unavailable, bad data), the agent still returns the base response text plus the figure. The user gets useful output even if the prose explanation fails.
- **Decision: use `msg.model_dump(exclude_unset=True)`** when appending the assistant message to avoid sending Pydantic-default `None` fields that confuse some model providers.

### 3c. Helper functions

```python
def _tool_error_message(tool_call_id: str, error: str) -> dict:
    return {"role": "tool", "tool_call_id": tool_call_id, "content": f"Error: {error}"}

def _try_parse_json(s: str) -> dict | None:
    try:
        return json.loads(s)
    except (json.JSONDecodeError, TypeError):
        return None
```

---

## Step 4: `src/agent/interpreter.py`

### 4a. `build_interpretation_prompt`

```python
def build_interpretation_prompt(df, site, plt_dtDoy, moisture_group) -> str:
    flat = df.reset_index()
    sub = flat[
        (flat["site"] == site)
        & (flat["plt_dtDoy"] == plt_dtDoy)
        & (flat["moisture_group"] == moisture_group)
    ].sort_values("composite", ascending=False)
    if sub.empty:
        raise ValueError(f"No data for site={site!r}, plt_dtDoy={plt_dtDoy!r}, moisture_group={moisture_group!r}")
    top3 = sub.head(3)
    rows_text = "\n".join(
        f"  #{i+1}: {row['trt_label']}  P(best)={row['P_best']:.1%}  "
        f"CVaR_20={row['CVaR_20']:.1f} bu/acre  composite={row['composite']:.3f}"
        for i, (_, row) in enumerate(top3.iterrows())
    )
    moisture_label = {"dry": "dry", "all": "average", "wet": "wet"}[moisture_group]
    return (
        f"You are an agronomic advisor. The following are the top 3 soybean management "
        f"combinations for the grid point nearest to site {site}, planted around "
        f"{plt_dtDoy}, under {moisture_label} year conditions:\n\n"
        f"{rows_text}\n\n"
        f"Write a plain-language explanation (≥150 words) for a Missouri Extension field agronomist. "
        f"Your explanation must cover: (1) why the #1 combination is recommended, referencing its "
        f"P(best) value and composite score; (2) the risk–return trade-off between the top 3 "
        f"(CVaR_20 measures yield in the worst 20% of simulated weather years); "
        f"(3) a brief caveat that this recommendation comes from the nearest grid point in the "
        f"trial network and actual performance may vary with local soil conditions. "
        f"Do not mention Python, Plotly, or data science terminology."
    )
```

Decision: the prompt is constructed entirely from data — no free-form instructions that differ per call. This keeps outputs consistent and testable (unit test can verify prompt structure without an LLM).

### 4b. `interpret`

Thin wrapper: call `build_interpretation_prompt`, pass to `litellm.completion` with no tools:
```python
def interpret(df, site, plt_dtDoy, moisture_group, model=LLM_MODEL) -> str:
    prompt = build_interpretation_prompt(df, site, plt_dtDoy, moisture_group)
    response = litellm.completion(
        model=model,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.choices[0].message.content
```

---

## Step 5: Tests (`tests/test_agent.py`)

| Test | Mark | What it checks |
|---|---|---|
| `test_tool_context_construction` | (none) | `ToolContext(dataset, grid)` stores attributes without error |
| `test_execute_tool_lookup` | (none) | `execute_tool("lookup_nearest_site", {"location": "Columbia, MO"}, ctx)` returns `ToolResult` with `figure=None` and `content` parseable as JSON — uses a mock geocoder that bypasses network |
| `test_execute_tool_recommendation` | (none) | `execute_tool("generate_recommendation_plot", {...}, ctx)` returns a `ToolResult` with `figure` as `go.Figure` — uses synthetic DataFrame and mock geocoder |
| `test_execute_tool_doy` | (none) | Same pattern for `generate_doy_response_plot` |
| `test_execute_tool_unknown_raises` | (none) | `execute_tool("nonexistent_tool", {}, ctx)` raises `AgentError` |
| `test_execute_tool_geocoding_error_returns_content` | (none) | When geocoder raises `GeocodingError`, tool returns `ToolResult` with non-empty `content` and `figure=None` (no exception propagates) |
| `test_build_interpretation_prompt` | (none) | `build_interpretation_prompt(df, site, plt_dtDoy, moisture_group)` returns a string containing `"P(best)"`, `"CVaR_20"`, and `"≥150 words"` — uses synthetic DataFrame, no LLM call |
| `test_build_interpretation_prompt_empty_raises` | (none) | Raises `ValueError` when filter returns zero rows |
| `test_agent_integration` | `@pytest.mark.llm` | Full `run_agent("Best soybean management for Audrain County in a dry spring", ctx)` returns `AgentResponse` with `figure` as `go.Figure`, `text` len ≥ 150, `site` not None — requires live Ollama or LLM API |

Unit tests (no mark) use a synthetic 12-row `SummaryDataset` (3 sites × 2 dates × 2 treatments, single moisture group) and a mock `KDTreeGrid` that always returns the same site. The mock geocoder is a simple function that returns a fixed `(lat, lon)` — injected via monkeypatching `src.geo.geocoder.geocode`.

---

## Step 6: Smoke Script (`scripts/smoke_phase2.py`)

```
1.  Load real dataset via load_dataset(AGGREGATE_CSV)
2.  Build grid via build_grid(dataset)
3.  Construct ToolContext(dataset, grid)
4.  Call run_agent("Show me the best soybean management for Audrain County in a dry spring", ctx)
      → assert isinstance(response.figure, go.Figure)
      → assert response.site is not None
      → assert len(response.text) >= 150
5.  Save response.figure as smoke_agent_recommendation.html
6.  Print resolved site, text length, and "Phase 2 OK."
```

Requires a running Ollama instance (or `YIELD_LLM_MODEL` set to a working API model). Document in the script header.

---

## Sequence Diagram

```
user_query
  │
  ▼
run_agent(user_query, ctx)
  │
  ├─ [messages = [system, user]]
  │
  ├─ ITERATION 1
  │    litellm.completion(model, messages, TOOLS)
  │    ──► tool_calls: [lookup_nearest_site("Audrain County, MO")]
  │    │
  │    ├─ execute_tool("lookup_nearest_site", args, ctx)
  │    │    geocode("Audrain County, MO") ──► (lat, lon)    [network]
  │    │    ctx.grid.nearest_site(lat, lon) ──► "39.419701_-92.425003"
  │    │    ──► ToolResult(content='{"site":"...","distance_deg":0.12}', figure=None)
  │    │
  │    └─ append assistant + tool result to messages
  │
  ├─ ITERATION 2
  │    litellm.completion(model, messages, TOOLS)
  │    ──► tool_calls: [generate_recommendation_plot("Audrain County, MO", "Apr-15", "dry")]
  │    │
  │    ├─ execute_tool("generate_recommendation_plot", args, ctx)
  │    │    resolve site (cached geocode result)
  │    │    plot_recommendation(df, site, "Apr-15", "dry") ──► go.Figure
  │    │    ──► ToolResult(content='{"site":...,"top_trt_label":...}', figure=go.Figure)
  │    │
  │    └─ append assistant + tool result to messages; capture figure, site
  │
  ├─ ITERATION 3
  │    litellm.completion(model, messages, TOOLS)
  │    ──► no tool_calls; final response text
  │    break
  │
  ├─ interpret(df, site, "Apr-15", "dry", model)
  │    build_interpretation_prompt(df, ...) ──► prompt str
  │    litellm.completion(model, [{"role":"user","content":prompt}])
  │    ──► explanation text (≥150 words)
  │
  └─ return AgentResponse(
         text = base_text + "---" + explanation,
         figure = go.Figure,
         site = "39.419701_-92.425003",
         raw_messages = [...]
     )
```
