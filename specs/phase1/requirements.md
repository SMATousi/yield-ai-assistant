# Phase 1 — Plot Engine: Requirements

## Functional Requirements

### FR-1: Shared Visual Theme (`src/plots/theme.py`)
- Export a `MOISTURE_COLORS` dict mapping each moisture group string to a hex colour:
  `{"dry": "#D85A30", "all": "darkgreen", "wet": "#185FA5"}` (matches R reference).
- Export a `HIGHLIGHT_COLORS` dict: `{"top": "#E31A1C", "other": "grey70"}`.
- Export an `MG_COLORSCALE` callable `mg_colors(mg_values: list[str]) -> dict[str, str]` that returns a colour-per-MG dict by interpolating a fixed 7-stop ramp (`["#2166AC", "#4DAC26", "#F7A400", "#D6604D", "#8B2FC9", "#A65628", "#E31A1C"]`) over the sorted unique MG values supplied. Output is deterministic for the same input set.
- Export layout constants: `BASE_FONT_SIZE = 11`, `TITLE_FONT_SIZE = 13`, `SUBTITLE_FONT_SIZE = 10`, `FIGURE_WIDTH = 1400`, `FIGURE_HEIGHT = 600`.
- All names are module-level constants or functions — no classes, no side effects at import time.

### FR-2: Recommendation Plot — Panel A (Ranked Dot Plot) (`src/plots/recommendation.py`)
- Implement `plot_recommendation(df, site, plt_dtDoy, moisture_group, top_n=3, show_n=20) -> go.Figure`.
- Filter `df` (a `pd.DataFrame` with MultiIndex on `(site, plt_dtDoy, moisture_group)`) to the exact `(site, plt_dtDoy, moisture_group)` combination; raise `ValueError` if the result is empty.
- Derive `trt_label` for every row: `f"MG{MG} · {pop/1000:.0f}k · {rs}in"` using the `MG`, `pop`, and `rs` columns.
- Sort all treatments by `P_best` descending; take the top `show_n` for Panel A.
- Assign `highlight = "top"` to the `top_n` highest-composite treatments, `"other"` to the rest.
- Panel A is a horizontal dot plot (`go.Scatter`, `mode="markers"`) with:
  - y-axis: `trt_label`, ordered by `P_best` ascending (lowest at bottom).
  - x-axis: `P_best`, formatted as percentage.
  - Asymmetric CI bars via `error_x` (`array = P_best_hi − P_best`, `arrayminus = P_best − P_best_lo`).
  - Marker colour: `HIGHLIGHT_COLORS[highlight]`; top treatments bold on y-axis tick text.
  - Hover template showing `trt_label` and `P_best` as percentage.
  - Rank badges (`#1`, `#2`, `#3`) as annotations positioned just right of `P_best_hi`.
  - `P_top3` italic annotation just left of `P_best_lo` for the top `top_n` treatments.

### FR-3: Recommendation Plot — Panel B (Risk–Return Bubble) (`src/plots/recommendation.py`)
- Panel B is a bubble chart (`go.Scatter`, `mode="markers"`) on the same figure:
  - x-axis: `CVaR_20` ("mean yield in worst 20% of years, bu/acre").
  - y-axis: `mean_yield` ("Mean yield, bu/acre").
  - Marker size scaled from `P_best` (map 0–max(P_best) to pixel range 4–20).
  - Marker colour: one colour per `MG` value using `mg_colors()` from `theme.py`.
  - Top `top_n` treatments rendered a second time with an open circle (unfilled) border.
  - Top `top_n` labelled with `trt_label` via `go.layout.Annotation`; placement must not obscure the point (nudge by 15 px right and up; no ggrepel equivalent needed for 3 labels).
  - Dashed reference lines at `median(CVaR_20)` (vertical) and `median(mean_yield)` (horizontal).
  - Quadrant annotations: "High yield / Low risk" (top-right) and "Low yield / High risk" (bottom-left) in grey italic.
- The two panels are assembled with `make_subplots(rows=1, cols=2, column_widths=[0.5, 0.5])`.
- Figure title = `"Soybean management recommendation"`, subtitle line = `"Site: {site}  |  Planting: {plt_dtDoy}  |  Scenario: {label}"` where `label` maps `"dry"→"Dry years"`, `"all"→"All years"`, `"wet"→"Wet years"`.
- Figure caption = `"Composite score weights: P_best 40% · P_top3 25% · CVaR 20% · Stability 15%"` rendered as a figure annotation at bottom-centre.

### FR-4: DOY Response Plot (`src/plots/doy_response.py`)
- Implement `plot_doy_response(df, site) -> go.Figure`.
- Filter `df` to the given `site`; raise `ValueError` if the result is empty.
- Derive `trt_label` identically to FR-2.
- Determine chronological planting-date order by parsing each `plt_dtDoy` string with `datetime.strptime(s, "%b-%d").replace(year=2000)` and sorting; use this order as the categorical x-axis sequence.
- For each of the three `moisture_group` values (`"dry"`, `"all"`, `"wet"`), identify the **winning treatment** at each planting date: the `trt` with the highest `composite` score for that `(plt_dtDoy, moisture_group)` combination. Any `trt` that is a winner in at least one `plt_dtDoy` within a moisture group is a **foreground treatment** for that group; all others are background.
- The figure uses `make_subplots(rows=3, cols=1, shared_xaxes=True)`, one row per moisture group (top→bottom: dry, all, wet).
- Per subplot:
  - Background traces: one `go.Scatter` per background `trt`, `mode="lines"`, colour `"grey80"`, `opacity=0.5`, `showlegend=False`.
  - Foreground traces: one `go.Scatter` per foreground `trt_label`, `mode="lines+markers"`, coloured by `trt_label` using a Set1-like palette (derived from `MOISTURE_COLORS` or a fixed qualitative ramp), `marker.size=5`.
  - Star markers: one `go.Scatter` per winning `(plt_dtDoy, moisture_group)` row, `mode="markers"`, `marker.symbol="star"`, `marker.size=12`, coloured by `trt_label`, `showlegend=False`.
  - `P_best` annotation as text just below each star (italic, `textposition="bottom center"`).
- x-axis label: `"Planting date"` (bottom subplot only). y-axis label: `"Mean yield (bu/acre)"` on each row.
- Subplot title for each row: `"Dry years"`, `"All years"`, `"Wet years"`.
- Overall figure title: `"Yield response to planting date — Site: {site}"`.

---

## Non-Functional Requirements

- `theme.py`, `recommendation.py`, and `doy_response.py` must be importable with no side effects (no data reads, no network calls, no figure renders at import time).
- No matplotlib anywhere in `src/plots/`. All output is `plotly.graph_objects.Figure`.
- `plot_recommendation` must raise `ValueError` with a message identifying the missing `(site, plt_dtDoy, moisture_group)` combination when there are zero rows after filtering.
- `plot_doy_response` must raise `ValueError` with a message identifying the site when there are zero rows after filtering.
- Both functions must complete in under 2 seconds on the full 172k-row aggregate DataFrame on developer hardware (the filtering step is cheap; no heavy computation at render time).

---

## Module Interface Contract

```python
# src/plots/theme.py
MOISTURE_COLORS: dict[str, str]          # {"dry": ..., "all": ..., "wet": ...}
HIGHLIGHT_COLORS: dict[str, str]         # {"top": ..., "other": ...}
BASE_FONT_SIZE: int
TITLE_FONT_SIZE: int
SUBTITLE_FONT_SIZE: int
FIGURE_WIDTH: int
FIGURE_HEIGHT: int

def mg_colors(mg_values: list[str]) -> dict[str, str]: ...

# src/plots/recommendation.py
def plot_recommendation(
    df: pd.DataFrame,
    site: str,
    plt_dtDoy: str,
    moisture_group: str,
    top_n: int = 3,
    show_n: int = 20,
) -> go.Figure: ...

# src/plots/doy_response.py
def plot_doy_response(
    df: pd.DataFrame,
    site: str,
) -> go.Figure: ...
```

The `df` argument in both plot functions is the `.df` attribute of `SummaryDataset` (MultiIndex on `site`, `plt_dtDoy`, `moisture_group`). Callers must reset the index before passing if they need flat column access — Decision: plot functions call `df.reset_index()` internally so callers do not need to.
