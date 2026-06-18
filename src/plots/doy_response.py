from __future__ import annotations

from datetime import datetime

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from src.plots.theme import (
    BASE_FONT_SIZE,
    FIGURE_WIDTH,
    TITLE_FONT_SIZE,
    fg_colors,
    make_trt_label,
)

_MOISTURE_ORDER = ["dry", "all", "wet"]
_MOISTURE_TITLES = {"dry": "Dry years", "all": "All years", "wet": "Wet years"}


def _doy_sort_key(plt_dtDoy: str) -> datetime:
    return datetime.strptime(plt_dtDoy, "%b-%d").replace(year=2000)


def _get_date_order(site_df: pd.DataFrame) -> list[str]:
    return sorted(site_df["plt_dtDoy"].unique(), key=_doy_sort_key)


def plot_doy_response(df: pd.DataFrame, site: str) -> go.Figure:
    flat = df.reset_index()
    site_df = flat[flat["site"] == site].copy()
    if site_df.empty:
        raise ValueError(f"No data for site={site!r}")

    site_df["trt_label"] = site_df.apply(make_trt_label, axis=1)
    date_order = _get_date_order(site_df)

    # ── Pre-compute winners and consistent colour map across all moisture groups
    winners_per_mg: dict[str, set[str]] = {}
    all_winning_labels: list[str] = []

    for mg in _MOISTURE_ORDER:
        mg_df = site_df[site_df["moisture_group"] == mg]
        if mg_df.empty:
            winners_per_mg[mg] = set()
            continue
        top1_idx = mg_df.groupby("plt_dtDoy")["composite"].idxmax()
        top1 = mg_df.loc[top1_idx]
        winning_trts = set(top1["trt"].tolist())
        winners_per_mg[mg] = winning_trts
        all_winning_labels.extend(
            mg_df[mg_df["trt"].isin(winning_trts)]["trt_label"].unique().tolist()
        )

    fg_color_map = fg_colors(all_winning_labels)

    # ── Build figure ──────────────────────────────────────────────────────────
    fig = make_subplots(
        rows=3,
        cols=1,
        shared_xaxes=True,
        subplot_titles=[_MOISTURE_TITLES[mg] for mg in _MOISTURE_ORDER],
        vertical_spacing=0.08,
    )

    for row_idx, mg in enumerate(_MOISTURE_ORDER, start=1):
        mg_df = site_df[site_df["moisture_group"] == mg].copy()
        if mg_df.empty:
            continue

        winning_trts = winners_per_mg[mg]
        d_bg = mg_df[~mg_df["trt"].isin(winning_trts)]
        d_fg = mg_df[mg_df["trt"].isin(winning_trts)]

        top1_idx = mg_df.groupby("plt_dtDoy")["composite"].idxmax()
        top1 = mg_df.loc[top1_idx].copy()

        # Background grey lines — one trace per trt to keep hover clean
        shown_bg_legend = False
        for trt_val, trt_rows in d_bg.groupby("trt"):
            ordered = trt_rows.set_index("plt_dtDoy").reindex(date_order).reset_index()
            fig.add_trace(
                go.Scatter(
                    x=ordered["plt_dtDoy"].tolist(),
                    y=ordered["mean_yield"].tolist(),
                    mode="lines",
                    line=dict(color="#CCCCCC", width=0.5),
                    opacity=0.5,
                    showlegend=False,
                    hoverinfo="skip",
                    name="other",
                ),
                row=row_idx, col=1,
            )

        # Foreground coloured lines — one trace per trt_label
        seen_labels: set[str] = set()
        for trt_val, trt_rows in d_fg.groupby("trt"):
            label = trt_rows["trt_label"].iloc[0]
            color = fg_color_map.get(label, "#888888")
            ordered = trt_rows.set_index("plt_dtDoy").reindex(date_order).reset_index()
            fig.add_trace(
                go.Scatter(
                    x=ordered["plt_dtDoy"].tolist(),
                    y=ordered["mean_yield"].tolist(),
                    mode="lines+markers",
                    line=dict(color=color, width=1.2),
                    marker=dict(color=color, size=5),
                    name=label,
                    legendgroup=label,
                    showlegend=(row_idx == 1 and label not in seen_labels),
                    hovertemplate=(
                        f"<b>{label}</b><br>"
                        "Planting: %{x}<br>"
                        "Mean yield: %{y:.1f} bu/acre<br>"
                        "<extra></extra>"
                    ),
                ),
                row=row_idx, col=1,
            )
            seen_labels.add(label)

        # Star markers at winning date × moisture, with P_best text
        star_colors = [fg_color_map.get(lbl, "#888888") for lbl in top1["trt_label"]]
        fig.add_trace(
            go.Scatter(
                x=top1["plt_dtDoy"].tolist(),
                y=top1["mean_yield"].tolist(),
                mode="markers+text",
                marker=dict(
                    symbol="star",
                    size=14,
                    color=star_colors,
                    line=dict(width=0.5, color="white"),
                ),
                text=[f"{p:.0%}" for p in top1["P_best"]],
                textposition="bottom center",
                textfont=dict(size=8, color="grey"),
                showlegend=False,
                hovertemplate=(
                    "<b>%{x} — winner</b><br>"
                    "Mean yield: %{y:.1f} bu/acre<br>"
                    "<extra></extra>"
                ),
                name=f"winner_{mg}",
            ),
            row=row_idx, col=1,
        )

    # ── Enforce chronological x order on all axes ─────────────────────────────
    fig.update_xaxes(
        categoryorder="array",
        categoryarray=date_order,
    )

    # ── Axis labels — bottom subplot only for x ───────────────────────────────
    fig.update_xaxes(title_text="Planting date", row=3, col=1)
    for r in range(1, 4):
        fig.update_yaxes(title_text="Mean yield (bu/acre)", row=r, col=1)

    fig.update_layout(
        title=dict(
            text=f"<b>Yield response to planting date</b><br>"
                 f"<span style='font-size:10px; color:grey;'>Site: {site}</span>",
            font=dict(size=TITLE_FONT_SIZE),
        ),
        font=dict(size=BASE_FONT_SIZE),
        width=FIGURE_WIDTH,
        height=900,
        legend=dict(orientation="v", x=1.01, y=1.0, xanchor="left"),
        plot_bgcolor="white",
        paper_bgcolor="white",
    )
    fig.update_xaxes(showgrid=True, gridcolor="rgba(0,0,0,0.06)")
    fig.update_yaxes(showgrid=True, gridcolor="rgba(0,0,0,0.06)")

    return fig
