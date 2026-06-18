# Tech Stack

## Guiding Principles

1. **Frontend-agnostic backend.** The backend is a pure Python service. The GUI (Gradio today, React tomorrow) attaches to it without requiring backend changes.
2. **No R at runtime.** The R visualisation code is ported to Python/Plotly. This eliminates the R + package dependency chain from the deployment environment.
3. **Aggregate-only at query time.** The atomic dataset is never loaded during a user session. All agent queries hit the in-memory aggregate DataFrame, keeping response times fast and memory bounded.
4. **Provider-agnostic LLM client.** The agent is not coupled to the Anthropic API. Switching to an Ollama-hosted open-source model (or any other provider) is a one-line config change.
5. **Lean dependency tree.** Each library is chosen because it does one thing well, not because it's the fashionable framework.

---

## Stack

### Language & Runtime

| Choice | Rationale |
|---|---|
| **Python 3.11+** | Matches the existing conda environment; strong ecosystem for data + LLM work. |
| **conda env `yield-ai`** | Reproducible environment via `environment.yml`; mirrors the graph-vls project convention. |

---

### LLM

| Component | Choice | Rationale |
|---|---|---|
| **Client layer** | **LiteLLM** | Unified OpenAI-style interface across 100+ providers (Ollama, Claude, OpenAI, Mistral, etc.). Switching providers is a one-line `MODEL=` config change with no other code changes. |
| **Default model** | `ollama/qwen2.5:14b` | Strong tool-use support among open-source models, runs fully locally, no API cost, data never leaves the machine. Requires ~16 GB RAM. `llama3.1:8b` is a lighter alternative (~8 GB RAM). |
| **Claude upgrade path** | `anthropic/claude-sonnet-4-6` | Drop-in replacement if open-source model quality proves insufficient for tool use or agronomic reasoning. No code changes required beyond setting `MODEL`. |

```python
# config.py — the only line that changes when switching providers
MODEL = os.getenv("YIELD_LLM_MODEL", "ollama/qwen2.5:14b")

# agent.py — provider-agnostic call
import litellm
response = litellm.completion(model=MODEL, messages=messages, tools=tools)
```

**Tool use caveat for open-source models:** Qwen2.5 and Llama 3.1/3.2 handle structured tool calls reasonably well, but output validation is still necessary — smaller or older models may hallucinate tool call syntax or ignore tools entirely. The agent's tool-use loop must include strict output validation and a graceful fallback for malformed tool responses.

Tool use (function calling) is the primary mechanism: the agent calls `generate_recommendation_plot`, `generate_doy_response_plot`, and `search_extension_knowledge` as structured tools, so figure generation and retrieval are deterministic — the LLM only provides reasoning, not raw data.

---

### Data Layer

| Component | Choice | Rationale |
|---|---|---|
| **Aggregate dataset** | Pandas `DataFrame` loaded at startup | The aggregate CSV is small enough to fit in memory; indexed with a MultiIndex on `(site, plt_dtDoy, moisture_group)` for O(1) lookups. |
| **Atomic dataset** | Not loaded at runtime | Upstream only; used offline to regenerate the aggregate. If ad-hoc atomic queries are needed in future, wrap in DuckDB. |
| **Grid nearest-neighbour** | `scipy.spatial.KDTree` | Sub-millisecond nearest-site lookup over the (lat, lon) coordinate grid. Built once at startup from the unique sites in the aggregate DataFrame. |

---

### Geocoding

| Choice | Rationale |
|---|---|
| **Nominatim via `geopy`** | Free, no API key required, covers US county/city/zip inputs well. Rate-limit: 1 req/s (acceptable for interactive use). |
| **US Census Geocoder (fallback)** | Handles ZIP codes and addresses that Nominatim misses; also free. |

The geocoder result is cached in a small in-memory dict keyed by normalised query string to avoid redundant API calls within a session.

---

### Visualisation

| Choice | Rationale |
|---|---|
| **Plotly (`plotly.graph_objects`)** | Interactive figures (hover, zoom, pan) that embed natively in Gradio. The R ggplot logic maps cleanly: `go.Scatter` for dot/line plots, `go.Scatter` with `mode='markers'` for bubble chart, `make_subplots` for patchwork-style layouts. |
| **No matplotlib** | Static output; interactive hover over treatment labels is essential for the recommendation plot. |

Key Plotly implementation notes:
- Panel A (recommendation): `go.Scatter` with `error_x` for CI bars; `row=1, col=1` in a 1×2 subplot grid.
- Panel B (risk–return): `go.Scatter` with `marker.size=P_best`; `ggrepel`-style label placement approximated with `textposition` + manual `textfont`.
- DOY response: `go.Scatter` per treatment, faceted via `row` index; star marker rendered as `marker.symbol='star'`.

---

### RAG Knowledge Base

| Component | Choice | Rationale |
|---|---|---|
| **PDF parsing** | `pypdf` | Lightweight, pure Python, handles standard extension PDF layout. |
| **Chunking** | `langchain_text_splitters.RecursiveCharacterTextSplitter` | 500-token chunks, 50-token overlap; proven default for agronomic prose. |
| **Embeddings** | `sentence-transformers` (`all-MiniLM-L6-v2`) | Fast, local, no API cost for ingestion. Can be swapped for Claude Embeddings API if retrieval quality is insufficient. |
| **Vector store** | **ChromaDB** (persistent, on-disk) | Lightweight, zero-infrastructure, runs embedded in the Python process. No separate server needed for 10–100 PDFs. |
| **Retrieval** | Top-k cosine similarity (k=4) | Returns chunks with source doc + page metadata for citation. |

---

### Agent Orchestration

No LangChain, LangGraph, or LlamaIndex agent framework — the orchestration loop is written directly against LiteLLM's completion API. This keeps the control flow transparent, avoids framework version-churn, and works identically regardless of which model is configured. The loop is ~80 lines:

```
user_message → litellm.completion(model, tools) → tool call? → execute tool → append result → litellm.completion → final text
```

Tools are plain Python functions decorated with a JSON schema descriptor. The same tool definitions work for Claude (native tool use) and Ollama models that support function calling.

---

### GUI

| Choice | Rationale |
|---|---|
| **Gradio `Blocks`** | Runs as a local desktop server (`localhost:7860`) or can be deployed to a VM with one command. Supports Plotly figures natively via `gr.Plot`. Multi-turn chat via `gr.Chatbot`. No frontend build step. |

Gradio is the correct choice here because:
- It handles local and hosted deployment without changing a line of code.
- `gr.Plot` renders Plotly figures interactively (hover, zoom) inside the chat interface.
- It is already familiar in the academic/extension research context.

If the project later needs a more polished UI, the Gradio layer can be replaced with a React frontend calling the same FastAPI backend — no backend changes required.

---

### API Layer (thin, optional in Phase 3)

| Choice | Rationale |
|---|---|
| **FastAPI** | Exposes `POST /query` and `GET /figure/{id}` endpoints. Allows the Gradio UI and any future frontend to share the same backend. Adds ~50 lines of code; enables the frontend-agnostic architecture. |

---

### Deployment

| Scenario | Approach |
|---|---|
| **Local (researcher laptop)** | `conda activate yield-ai && python src/app/app.py` — Gradio opens at `localhost:7860`. |
| **Hosted VM (MU Extension server)** | `Docker` container; `docker compose up` starts FastAPI + Gradio on port 80. nginx reverse proxy handles TLS. |

---

### Testing

| Tool | Scope |
|---|---|
| `pytest` | Unit tests (grid lookup, geocoder, plot trace counts) and integration tests (end-to-end agent query). |
| `pytest-snapshot` | Plotly figure structure snapshots (traces, axes) for visual regression. |

---

## Dependency Summary

```
litellm            # provider-agnostic LLM client (Claude, Ollama, OpenAI, …)
gradio             # GUI
plotly             # interactive visualisation
fastapi            # API layer
uvicorn            # ASGI server
pandas             # data layer
scipy              # KD-tree grid matching
geopy              # geocoding
pypdf              # PDF parsing
langchain-text-splitters  # chunking
sentence-transformers     # embeddings
chromadb           # vector store
pytest             # testing
```

To switch to Claude if needed:

```bash
YIELD_LLM_MODEL=anthropic/claude-sonnet-4-6 python src/app/app.py
```

All packages available on PyPI; no compiled extensions beyond numpy/scipy (already in the conda base).
