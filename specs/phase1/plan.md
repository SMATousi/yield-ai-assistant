# Phase 1 — Plot Engine: Implementation Plan

## Overview

Port the two R ggplot2 visualisations to interactive Python/Plotly figures. This phase produces three new modules under `src/plots/` and their tests. It does not touch the agent, geocoder, or GUI — it only consumes the `SummaryDataset.df` DataFrame produced by Phase 0 and returns `plotly.graph_objects.Figure` objects.

Reference material: `data/Data for Ali/12.5_Sample figures.Rmd` (R source), `data/Data for Ali/Rankrecommendation_plot.png` and `data/Data for Ali/doy_response_top1.png` (reference PNGs).

---

## Step 1: Scaffolding

Create `src/plots/` with init files:

```
src/plots/
  __init__.py
  theme.py
  recommendation.py
  doy_response.py
tests/
  test_plots.py          # new
scripts/
  smoke_phase1.py        # new
```

No new dependencies beyond `plotly`, which is already in `environment.yml`.

---

## Step 2: `src/plots/theme.py`

Define all visual constants that both plot modules share. Nothing here performs computation at import time.

1. `MOISTURE_COLORS` — taken verbatim from the R code: `{"dry": "#D85A30", "all": "darkgreen", "wet": "#185FA5"}`.
2. `HIGHLIGHT_COLORS` — `{"top": "#E31A1C", "other": "grey70"}`.
3. `mg_colors(mg_values)`:
   - Sort the incoming list of MG strings.
   - Interpolate the 7-stop colour ramp over `n = len(mg_values)` stops using `matplotlib.colors.LinearSegmentedColormap` or a pure-Python linear interpolation (no matplotlib import needed — implement a simple RGB lerp over the 7 stops).
   - Decision: implement the lerp without matplotlib to avoid adding a dependency for a single utility. The R `colorRampPalette` logic is straightforward hex → RGB → interpolate → hex.
4. Layout constants: `BASE_FONT_SIZE`, `TITLE_FONT_SIZE`, `SUBTITLE_FONT_SIZE`, `FIGURE_WIDTH`, `FIGURE_HEIGHT`.

---

## Step 3: `src/plots/recommendation.py`

### 3a. Internal helpers

```python
def _make_trt_label(row) -> str:
    return f"MG{row['MG']} · {row['pop']/1000:.0f}k · {row['rs']}in"

def _filter_recommendation(df, site, plt_dtDoy, moisture_group) -> pd.DataFrame:
    # reset_index(), filter, raise ValueError if empty
```

### 3b. `plot_recommendation`

Follow this construction order — Plotly subplot state must be set up before traces are added:

1. Call `make_subplots(rows=1, cols=2, column_widths=[0.5, 0.5], subplot_titles=["A · Ranked by P(best)", "B · Risk–return space"])`.
2. Build the filtered + ranked DataFrame. Sort by `P_best` descending; assign `overall_rank`, `highlight`, `trt_label`. Take `d_dot = top show_n by P_best`.
3. **Panel A traces** (added to `row=1, col=1`):
   - One `go.Scatter` for all `show_n` points (CI bars via `error_x`).
   - Separate `go.Scatter` for top `top_n` points overlaid in highlight colour (so they render on top).
   - `go.layout.Annotation` objects for rank badges (`#1`, `#2`, `#3`) and `P_top3` italic labels.
4. **Panel B traces** (added to `row=1, col=2`):
   - One `go.Scatter` per MG value for all treatments (colour = MG).
   - One `go.Scatter` for the top `top_n` treatments with `marker.symbol="circle-open"`, `marker.line.width=2`.
   - Median reference lines as `go.Scatter` with `mode="lines"`, `line.dash="dash"`.
   - Quadrant annotations via `fig.add_annotation`.
5. Set figure title and subtitle via `fig.update_layout(title=...)`.
6. Apply `FIGURE_WIDTH`, `FIGURE_HEIGHT`, `BASE_FONT_SIZE` to `fig.update_layout`.

Key Plotly gotchas:
- `error_x` in `go.Scatter` uses `array` (upper delta) and `arrayminus` (lower delta), not absolute values.
- Y-axis in Panel A is categorical; set `yaxis.type="category"` and pass ordered label list as `yaxis.categoryarray` to enforce P_best-ascending order.
- Subplot axes are named `xaxis`, `xaxis2`, `yaxis`, `yaxis2` — use `fig.update_xaxes(row=1, col=N)` to avoid ambiguity.

---

## Step 4: `src/plots/doy_response.py`

### 4a. Internal helpers

```python
def _doy_sort_key(plt_dtDoy: str) -> datetime:
    return datetime.strptime(plt_dtDoy, "%b-%d").replace(year=2000)

def _get_date_order(site_df: pd.DataFrame) -> list[str]:
    return sorted(site_df["plt_dtDoy"].unique(), key=_doy_sort_key)
```

### 4b. `plot_doy_response`

Construction order:

1. Reset index, filter to `site`, raise if empty.
2. Compute `date_order` list (chronological).
3. For each `moisture_group` in `["dry", "all", "wet"]`:
   a. Find the top-composite treatment per `plt_dtDoy` → `top1_per_doy` (one row per date).
   b. Identify foreground `trt` values: any `trt` appearing in `top1_per_doy`.
   c. Split `site_df` filtered to this moisture group into `d_bg` (background) and `d_fg` (foreground).
4. Call `make_subplots(rows=3, cols=1, shared_xaxes=True, subplot_titles=["Dry years", "All years", "Wet years"], vertical_spacing=0.08)`.
5. Per moisture group row `r` (1=dry, 2=all, 3=wet):
   - Add one background `go.Scatter` per `trt` in `d_bg` (`mode="lines"`, grey, `showlegend=False`).
   - Add one foreground `go.Scatter` per `trt_label` in `d_fg` (`mode="lines+markers"`, coloured).
   - Add one star `go.Scatter` per row in `top1_per_doy` (`marker.symbol="star"`, `showlegend=False`).
   - Add text annotations for `P_best` below each star.
6. Set `xaxis.categoryorder="array"` and `xaxis.categoryarray=date_order` on all three x-axes to enforce chronological x ordering.
7. Apply overall figure title and dimensions.

Key Plotly gotcha: `shared_xaxes=True` means `xaxis3` (bottom subplot) is the visible one; set tick label rotation there, not on `xaxis` or `xaxis2`.

---

## Step 5: Tests (`tests/test_plots.py`)

| Test | What it checks |
|---|---|
| `test_recommendation_trace_count` | `plot_recommendation` returns a Figure with ≥ 2 traces in col=1 and ≥ 1 trace in col=2 |
| `test_recommendation_hover_template` | At least one Panel A trace has a `hovertemplate` containing `"P(best)"` |
| `test_recommendation_error_x_present` | At least one Panel A trace has `error_x` set and `error_x.visible == True` |
| `test_recommendation_empty_raises` | `plot_recommendation` with a nonexistent site raises `ValueError` |
| `test_doy_response_subplot_count` | `plot_doy_response` returns a Figure with `len(fig._grid_ref) == 3` rows |
| `test_doy_response_star_present` | At least one trace in the DOY response figure has `marker.symbol == "star"` |
| `test_doy_response_x_order` | The x-axis `categoryarray` of the DOY figure equals the correct chronological order |
| `test_doy_response_empty_raises` | `plot_doy_response` with a nonexistent site raises `ValueError` |
| `test_theme_mg_colors_deterministic` | `mg_colors(["3.9", "4.2", "4.5"])` returns the same dict on two calls |
| `test_theme_no_side_effects` | Importing `src.plots.theme` does not create any files or network calls |

All tests use a small synthetic DataFrame (5 sites × 3 planting dates × 3 moisture groups × 4 treatments) rather than the real 172k-row CSV to keep unit tests fast and offline.

---

## Step 6: Smoke Script (`scripts/smoke_phase1.py`)

```
1. Load real dataset via load_dataset(AGGREGATE_CSV)
2. Build grid
3. Call plot_recommendation(ds.df, "39.419701_-92.425003", "Apr-15", "all")
   → assert isinstance(fig, go.Figure)
   → save as smoke_recommendation.html
4. Call plot_doy_response(ds.df, "39.419701_-92.425003")
   → assert isinstance(fig, go.Figure)
   → save as smoke_doy_response.html
5. Print trace counts and "Phase 1 OK."
```

Open the saved HTMLs in a browser to verify interactive hover works.

---

## Sequence Diagram

```
caller (agent or smoke script)
  │
  ├─ load_dataset(AGGREGATE_CSV) ──────────────► SummaryDataset.df
  │
  ├─ plot_recommendation(df, site, doy, moisture)
  │     │
  │     ├─ _filter_recommendation(df, ...) ────► filtered pd.DataFrame
  │     ├─ rank + label rows
  │     ├─ make_subplots(rows=1, cols=2)
  │     ├─ add Panel A traces (go.Scatter + error_x)
  │     ├─ add Panel B traces (go.Scatter bubbles)
  │     └─ update_layout ──────────────────────► go.Figure
  │
  └─ plot_doy_response(df, site)
        │
        ├─ _get_date_order(site_df) ──────────► sorted list[str]
        ├─ compute top1_per_doy per moisture
        ├─ split bg / fg treatments
        ├─ make_subplots(rows=3, cols=1)
        ├─ add traces per moisture row
        └─ update_layout ──────────────────────► go.Figure
```
