# Roadmap

Each phase ends with a working, testable deliverable. Phases are sequential; each builds on the previous.

---

## Phase 0 — Data Layer
**Goal:** Load the aggregate dataset and resolve any user-specified location to the nearest grid point.

**Deliverables:**
- `src/data/loader.py` — loads `ExampleData_aggregate.csv` into a Pandas DataFrame at startup; validates required columns; exposes a typed `SummaryDataset` wrapper.
- `src/data/grid.py` — builds a KD-tree over all (lat, lon) grid points; `nearest_site(lat, lon) → site_str` returns the matching `site` key in under 1 ms.
- `src/geo/geocoder.py` — wraps a geocoding backend (Nominatim via geopy, with fallback to Census Geocoder) to convert free-text location → (lat, lon).
- Unit tests: grid lookup correctness, geocoder round-trip on 5 Missouri cities.

**Validation gate:** Given "Columbia, MO", the system returns a site string whose lat/lon is within 0.5° of Columbia's true coordinates.

---

## Phase 1 — Plot Engine
**Goal:** Port both R visualizations to Python/Plotly; output must match the R reference figures in structure and information density.

**Deliverables:**
- `src/plots/recommendation.py` — `plot_recommendation(df, site, plt_dtDoy, moisture_group, top_n=3, show_n=20) → plotly.Figure` — two-panel layout: ranked P(best) dot plot with CI bars (Panel A) and risk–return bubble chart (Panel B).
- `src/plots/doy_response.py` — `plot_doy_response(df, site) → plotly.Figure` — three-facet line chart (dry / all / wet), winning treatments coloured, star markers at winning DOY × moisture.
- `src/plots/theme.py` — shared colour palettes, font sizes, and axis formatting constants so both plots share a consistent visual identity.
- Visual regression tests: save reference PNGs from R; compare Plotly output structure (traces, axes, panel count) in CI.

**Validation gate:** Both plots render for site `39.419701_-92.425003` and match the reference PNG layout. Interactive hover shows treatment label and P(best) value.

---

## Phase 2 — Agent Core
**Goal:** A Claude-powered agent that parses a natural-language query, calls the right plot function as a tool, and returns a figure + plain-language interpretation.

**Deliverables:**
- `src/agent/tools.py` — three tool definitions for Claude tool use:
  - `generate_recommendation_plot(location, planting_date, moisture_scenario)`
  - `generate_doy_response_plot(location)`
  - `lookup_nearest_site(location)` (utility, also used internally)
- `src/agent/agent.py` — orchestration loop: sends user message to Claude API (claude-sonnet-4-6), handles tool calls, returns `AgentResponse(figure, text)`.
- `src/agent/interpreter.py` — post-plot prompt that instructs Claude to explain the top 3 treatments, the risk–return trade-off, and any caveats about the grid resolution.
- Integration test: end-to-end query "Best management for Audrain County in a dry spring" → recommendation plot + ≥150 word interpretation.

**Validation gate:** The agent correctly identifies the moisture scenario from natural language ("dry spring", "wet year", "average conditions"), resolves the location, and produces a plot without manual intervention.

---

## Phase 3 — GUI
**Goal:** A chat-style GUI where users type queries and see rendered figures inline.

**Deliverables:**
- `src/app/app.py` — Gradio `Blocks` application:
  - Chat input box (full-width, multi-turn).
  - Plot panel (right side) that renders the most recent Plotly figure interactively.
  - Source citations panel (collapsible) showing RAG passages used.
  - "Clear" and "Download figure" buttons.
- `src/app/state.py` — session state managing conversation history and cached site lookups.
- `Dockerfile` — containerised deployment so it can run locally (`docker run`) or be hosted on a VM.
- Manual test checklist against 5 representative queries covering both plot types and a RAG question.

**Validation gate:** A non-technical user can go from typing a county name to seeing a recommendation plot and reading a plain-language explanation in under 10 seconds, with no error messages.

---

## Phase 4 — RAG Knowledge Base
**Goal:** Ingest MU Extension PDFs; enable the agent to ground agronomic explanations in retrieved passages.

**Deliverables:**
- `src/rag/ingest.py` — PDF chunking (recursive character splitter, ~500 tokens, 50-token overlap) and embedding via the Claude Embeddings API or `sentence-transformers`; stores vectors in ChromaDB on disk.
- `src/rag/retriever.py` — `retrieve(query, k=4) → list[Chunk]` with source citation metadata (document name, page number).
- Agent integration: retrieved passages injected into the system prompt when the user asks a "why" or "how" question; tool `search_extension_knowledge(query)` added to the agent's tool set.
- Validation: retrieval recall test on 10 hand-crafted questions whose answers are known to appear in the PDFs.

**Validation gate:** For the query "Why does row spacing affect yield more in dry years?", the agent cites at least one extension document by name and page.

---

## Phase 5 — Hardening & Deployment
**Goal:** Make the system reliable enough for MU Extension field use, with an expert review workflow that lets agronomists audit AI outputs before trusting recommendations in production.

**Deliverables:**
- `src/app/validation.py` — `ValidationWriter` class and `make_validation_writer` factory. Activated by `--validate` CLI flag or `YIELD_VALIDATE=1`. Writes per-turn artifacts (query, response text, full message JSON, HTML figures) under a timestamped session directory, and regenerates a self-contained `index.html` after each turn for offline expert review.
- `src/app/spend.py` — daily API cost tracking. Reads/writes a JSON file keyed by UTC date; rejects queries when accumulated spend exceeds `YIELD_MAX_DAILY_USD` (default $5).
- Error handling for: unrecognised location, site with no data for requested DOY/moisture, LLM API timeout (`YIELD_LLM_TIMEOUT`, default 60 s).
- Rate limiting: per-session token cap via `YIELD_MAX_SESSION_TOKENS` (default 50 000).
- Operational logging: one JSON line per completed turn to stdout (`ts`, `query`, `site`, `plot_types`, `model`, `latency_s`, `input_tokens`, `output_tokens`).
- Deployment guide: README instructions for local Docker run and for hosting on a single VM (DigitalOcean / AWS Lightsail tier), including how to mount the validation output directory as a Docker volume.
- Optional: simple password gate (HTTP Basic Auth via nginx) if hosted externally.

**Validation gate:** An agronomist can run `python src/app/app.py --validate`, submit 5 representative queries, then open `validation_runs/<session>/index.html` in a browser (no server required) and review all queries, responses, and figures without launching the app again.

---

## Future (not scoped)

- Spatial weather maps by phenological stage (R1–R7).
- Cross-site comparison plots (multi-site ranking for a given treatment).
- Dataset refresh pipeline (re-run aggregate from new atomic data without code changes).
- Public-facing deployment with full auth and multi-tenancy.
