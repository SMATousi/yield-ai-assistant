# Phase 1 — Plot Engine: Validation

## Gate Criterion (from Roadmap)

> Both plots render for site `39.419701_-92.425003` and match the reference PNG layout. Interactive hover shows treatment label and P(best) value.

This is the single pass/fail gate. All checklist items below must be green before Phase 2 begins.

Note: `39.419701_-92.425003` is confirmed present in the aggregate dataset (used as the example site in `12.5_Sample figures.Rmd`).

---

## Checklist

### theme.py

- [x] `from src.plots.theme import MOISTURE_COLORS, HIGHLIGHT_COLORS, mg_colors` imports without error and without any file I/O or network calls.
- [x] `MOISTURE_COLORS["dry"] == "#D85A30"`, `MOISTURE_COLORS["all"] == "darkgreen"`, `MOISTURE_COLORS["wet"] == "#185FA5"`.
- [x] `HIGHLIGHT_COLORS["top"] == "#E31A1C"`.
- [x] `mg_colors(["3.9", "4.2"])` returns a dict with exactly 2 keys and hex-string values starting with `"#"`.
- [x] `mg_colors(["3.9", "4.2", "4.5"])` returns the same dict on a second call (deterministic).
- [x] `mg_colors([])` returns an empty dict without error.

### recommendation.py — structure

- [x] `plot_recommendation(df, "39.419701_-92.425003", "Apr-15", "all")` returns a `plotly.graph_objects.Figure` without error.
- [x] The returned figure has exactly 2 subplot columns (`len(fig._grid_ref[0]) == 2`).
- [x] Panel A has at least 2 traces (dot trace + CI trace, or equivalent).
- [x] At least one Panel A trace has `error_x` set with `visible=True`.
- [x] At least one Panel A trace has a `hovertemplate` containing the substring `"P(best)"`.
- [x] Panel A y-axis category order is ascending by `P_best` (lowest treatment at the bottom).
- [x] Panel B has at least one trace with `marker.size` values that vary across points (bubble sizing is active).
- [x] The figure has dashed vertical and horizontal reference lines in Panel B (traces with `line.dash="dash"`).

### recommendation.py — content

- [x] With `top_n=3`, exactly 3 treatments are coloured `"#E31A1C"` in Panel A.
- [x] The figure title contains `"39.419701_-92.425003"` and `"Apr-15"`.
- [x] With `show_n=20`, Panel A contains exactly 20 treatment rows (or fewer if the filtered data has fewer than 20 rows).
- [x] `plot_recommendation(df, "nonexistent_site", "Apr-15", "all")` raises `ValueError`.
- [x] `plot_recommendation(df, "39.419701_-92.425003", "Jan-01", "all")` raises `ValueError` (date not in data).

### doy_response.py — structure

- [x] `plot_doy_response(df, "39.419701_-92.425003")` returns a `plotly.graph_objects.Figure` without error.
- [x] The returned figure has exactly 3 subplot rows (`len(fig._grid_ref) == 3`).
- [x] At least one trace in the figure has `marker.symbol == "star"`.
- [x] The x-axis `categoryarray` of subplot row 1 equals the chronologically sorted list of planting dates for that site (e.g. `["Mar-15", "Apr-01", "Apr-15", ...]`, not alphabetical).
- [x] Background traces (grey) have `showlegend=False`.
- [x] Foreground traces have `showlegend=True` (or are distinguishable by colour).

### doy_response.py — content

- [x] The subplot titles are `"Dry years"`, `"All years"`, `"Wet years"` (top to bottom).
- [x] The figure title contains `"39.419701_-92.425003"`.
- [x] `plot_doy_response(df, "nonexistent_site")` raises `ValueError`.

### Code quality

- [x] `pytest tests/test_plots.py -v` passes all 15 unit tests with zero failures using the synthetic DataFrame (offline, no CSV loaded).
- [x] `scripts/smoke_phase1.py` runs to completion, saves `smoke_recommendation.html` and `smoke_doy_response.html`, and prints `"Phase 1 OK."`.
- [x] Opening `smoke_recommendation.html` in a browser: hovering over a dot in Panel A shows the treatment label and P(best) percentage.
- [x] Opening `smoke_doy_response.html` in a browser: star markers are visible at the winning planting date in each of the 3 moisture facets.
- [x] Neither `recommendation.py` nor `doy_response.py` imports `matplotlib` anywhere.

---

## Smoke Output (recorded 2026-06-17)

```
Loading dataset...
  172,152 rows, 203 unique sites
Rendering recommendation plot for 39.419701_-92.425003 / Apr-15 / all...
  Traces: 11  →  saved smoke_recommendation.html
Rendering DOY response plot for 39.419701_-92.425003...
  Traces: 111  →  saved smoke_doy_response.html

Phase 1 OK.
```

## How to Run Validation

```bash
# Unit tests (synthetic data, no CSV, offline)
conda run -n yield-ai pytest tests/test_plots.py -v

# Smoke test (requires real CSV at data/Data for Ali/ExampleData_aggregate.csv)
conda run -n yield-ai python scripts/smoke_phase1.py

# Then open the output files in a browser
open smoke_recommendation.html
open smoke_doy_response.html
```
