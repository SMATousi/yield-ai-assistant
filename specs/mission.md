# Mission

## Problem

Soybean producers and their advisors in Missouri face dozens of interacting management decisions each season — maturity group, planting date, seeding rate, and row spacing — whose optimal combination shifts with location, soil, and weather regime. Existing guidance is either too generic (county-wide averages) or too technical (raw trial data) for practical field use. Advisors need a tool that can translate a natural-language question ("What should I plant at my farm in early April in a dry year?") into a defensible, site-specific recommendation backed by 30 years of simulated weather scenarios.

## What This System Does

The yield AI assistant is a conversational agent that:

1. **Resolves location** from any user input (county name, town, zip code, address) to the nearest point in the soybean management trial grid.
2. **Generates visualizations** on demand — a ranked recommendation plot (P(best) + risk–return space) and a planting-date response curve — using the pre-computed aggregate dataset.
3. **Interprets results in plain language**, explaining what the top combinations are, why they perform well, and what trade-offs exist between high mean yield and downside risk.
4. **Answers agronomic questions** using a retrieval-augmented knowledge base built from MU Extension publications, grounding its reasoning in peer-reviewed extension science rather than hallucination.

## Datasets

| Dataset | Role | Access pattern |
|---|---|---|
| `ExampleData_aggregate.csv` | Empirical performance metrics (P_best, CVaR, composite score, yield quantiles) per site × planting date × treatment × moisture regime | Loaded into memory at startup; all agent queries hit this |
| `ExampleData_atomic.csv` | Individual year-level simulation rows; large | Upstream only — used offline to regenerate the aggregate; never queried at runtime |

**Aggregate schema** (key columns): `site` (lat_lon string), `plt_dtDoy` (e.g. `Apr-15`), `trt` (e.g. `3.9_90000_15` = MG · pop · row spacing), `moisture_group` (dry / all / wet), `P_best`, `P_top3`, `CVaR_20`, `composite`, yield quantiles (q10–q90).

## Target Users

MU Extension field agronomists and crop advisors serving producers across Missouri (~10–100 concurrent users). Users are comfortable with agronomic terminology but not with data science; they expect plain-language outputs and publication-quality figures.

## Success Criteria

- A user can describe their farm location in any natural-language form and receive a correctly matched grid point within 2 seconds.
- The recommendation plot and DOY response curve render interactively within 5 seconds of the query.
- The agent's plain-language interpretation references the composite score methodology and at least one relevant extension principle from the RAG corpus.
- The system handles all Missouri grid points in the aggregate dataset without hardcoding.

## Non-Goals (v1)

- Real-time weather data or seasonal forecasts.
- Irrigation scheduling or nutrient management (separate domains).
- Crop types other than soybean.
- Authentication / multi-tenant data isolation (deferred to v2 if public-facing).
- Training or fine-tuning the underlying NN; the aggregate dataset is a fixed input.
