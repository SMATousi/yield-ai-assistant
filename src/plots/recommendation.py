from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from src.plots.theme import (
    BASE_FONT_SIZE,
    FIGURE_HEIGHT,
    FIGURE_WIDTH,
    HIGHLIGHT_COLORS,
    SUBTITLE_FONT_SIZE,
    TITLE_FONT_SIZE,
    make_trt_label,
    mg_colors,
)

_MOISTURE_LABELS = {"dry": "Dry years", "all": "All years", "wet": "Wet years"}


def _filter_recommendation(
    df: pd.DataFrame,
    site: str,
    plt_dtDoy: str,
    moisture_group: str,
) -> pd.DataFrame:
    flat = df.reset_index()
    d = flat[
        (flat["site"] == site)
        & (flat["plt_dtDoy"] == plt_dtDoy)
        & (flat["moisture_group"] == moisture_group)
    ].copy()
    if d.empty:
        raise ValueError(
            f"No data for site={site!r}, plt_dtDoy={plt_dtDoy!r}, "
            f"moisture_group={moisture_group!r}"
        )
    return d


def _scale_bubble(p_best: pd.Series, min_px: float = 4, max_px: float = 20) -> list[float]:
    max_val = p_best.max()
    if max_val == 0:
        return [min_px] * len(p_best)
    return (min_px + (p_best / max_val) * (max_px - min_px)).tolist()


def plot_recommendation(
    df: pd.DataFrame,
    site: str,
    plt_dtDoy: str,
    moisture_group: str,
    top_n: int = 3,
    show_n: int = 20,
) -> go.Figure:
    d = _filter_recommendation(df, site, plt_dtDoy, moisture_group)

    d["trt_label"] = d.apply(make_trt_label, axis=1)
    d = d.sort_values("composite", ascending=False).reset_index(drop=True)
    d["overall_rank"] = d.index + 1
    d["highlight"] = d["overall_rank"].apply(lambda r: "top" if r <= top_n else "other")
    d["top_label"] = d["overall_rank"].apply(
        lambda r: f"#{r}" if r <= min(top_n, 3) else None
    )

    d_dot = d.nlargest(show_n, "P_best").copy()
    category_order = d_dot.sort_values("P_best", ascending=True)["trt_label"].tolist()

    top_df = d[d["highlight"] == "top"]
    top_dot = d_dot[d_dot["highlight"] == "top"]

    mg_color_map = mg_colors([str(v) for v in d["MG"].unique()])
    moisture_label = _MOISTURE_LABELS.get(moisture_group, moisture_group)

    fig = make_subplots(
        rows=1,
        cols=2,
        column_widths=[0.5, 0.5],
        subplot_titles=["A · Ranked by P(best)", "B · Risk–return space"],
        horizontal_spacing=0.12,
    )

    # ── Panel A: other (grey) dots ─────────────────────────────────────────────
    d_other = d_dot[d_dot["highlight"] == "other"]
    fig.add_trace(
        go.Scatter(
            x=d_other["P_best"].tolist(),
            y=d_other["trt_label"].tolist(),
            mode="markers",
            marker=dict(
                color=HIGHLIGHT_COLORS["other"],
                size=8,
                symbol="circle",
                line=dict(color=HIGHLIGHT_COLORS["other"], width=1),
            ),
            error_x=dict(
                type="data",
                symmetric=False,
                array=(d_other["P_best_hi"] - d_other["P_best"]).tolist(),
                arrayminus=(d_other["P_best"] - d_other["P_best_lo"]).tolist(),
                visible=True,
                color=HIGHLIGHT_COLORS["other"],
                thickness=1.5,
            ),
            name="other",
            showlegend=False,
            hovertemplate=(
                "<b>%{y}</b><br>"
                "P(best): %{x:.1%}<br>"
                "<extra></extra>"
            ),
        ),
        row=1, col=1,
    )

    # ── Panel A: top (red) dots overlaid ──────────────────────────────────────
    fig.add_trace(
        go.Scatter(
            x=top_dot["P_best"].tolist(),
            y=top_dot["trt_label"].tolist(),
            mode="markers",
            marker=dict(
                color=HIGHLIGHT_COLORS["top"],
                size=10,
                symbol="circle",
                line=dict(color=HIGHLIGHT_COLORS["top"], width=1.5),
            ),
            error_x=dict(
                type="data",
                symmetric=False,
                array=(top_dot["P_best_hi"] - top_dot["P_best"]).tolist(),
                arrayminus=(top_dot["P_best"] - top_dot["P_best_lo"]).tolist(),
                visible=True,
                color=HIGHLIGHT_COLORS["top"],
                thickness=1.5,
            ),
            name="top",
            showlegend=False,
            hovertemplate=(
                "<b>%{y}</b><br>"
                "P(best): %{x:.1%}<br>"
                "<extra></extra>"
            ),
        ),
        row=1, col=1,
    )

    # ── Panel A: rank badge and P_top3 annotations ────────────────────────────
    for _, row in top_dot.iterrows():
        # Rank badge right of CI bar
        fig.add_annotation(
            x=row["P_best_hi"] + 0.005,
            y=row["trt_label"],
            text=f"<b>{row['top_label']}</b>",
            showarrow=False,
            font=dict(color=HIGHLIGHT_COLORS["top"], size=11),
            xref="x", yref="y",
            xanchor="left",
        )
        # P_top3 italic left of CI bar
        fig.add_annotation(
            x=row["P_best_lo"] - 0.003,
            y=row["trt_label"],
            text=f"<i>Top3={row['P_top3']:.0%}</i>",
            showarrow=False,
            font=dict(color="grey", size=9),
            xref="x", yref="y",
            xanchor="right",
        )

    # ── Panel B: all treatments coloured by MG ────────────────────────────────
    for mg_val, mg_group in d.groupby("MG"):
        mg_str = str(mg_val)
        color = mg_color_map.get(mg_str, "#888888")
        fig.add_trace(
            go.Scatter(
                x=mg_group["CVaR_20"].tolist(),
                y=mg_group["mean_yield"].tolist(),
                mode="markers",
                marker=dict(
                    size=_scale_bubble(mg_group["P_best"]),
                    color=color,
                    opacity=0.5,
                ),
                name=f"MG {mg_str}",
                customdata=list(
                    zip(
                        mg_group["trt_label"].tolist(),
                        mg_group["P_best"].tolist(),
                        mg_group["composite"].tolist(),
                    )
                ),
                hovertemplate=(
                    "<b>%{customdata[0]}</b><br>"
                    "CVaR₂₀: %{x:.1f} bu/acre<br>"
                    "Mean yield: %{y:.1f} bu/acre<br>"
                    "P(best): %{customdata[1]:.1%}<br>"
                    "<extra></extra>"
                ),
            ),
            row=1, col=2,
        )

    # ── Panel B: top treatments with open-circle border ───────────────────────
    fig.add_trace(
        go.Scatter(
            x=top_df["CVaR_20"].tolist(),
            y=top_df["mean_yield"].tolist(),
            mode="markers",
            marker=dict(
                size=_scale_bubble(top_df["P_best"], min_px=8, max_px=22),
                color="rgba(0,0,0,0)",
                symbol="circle-open",
                line=dict(color=HIGHLIGHT_COLORS["top"], width=2),
            ),
            showlegend=False,
            hoverinfo="skip",
        ),
        row=1, col=2,
    )

    # ── Panel B: median reference lines ───────────────────────────────────────
    med_cvar = float(d["CVaR_20"].median())
    med_yield = float(d["mean_yield"].median())
    y_lo, y_hi = float(d["mean_yield"].min()), float(d["mean_yield"].max())
    x_lo, x_hi = float(d["CVaR_20"].min()), float(d["CVaR_20"].max())

    fig.add_trace(
        go.Scatter(
            x=[med_cvar, med_cvar], y=[y_lo, y_hi],
            mode="lines",
            line=dict(dash="dash", color="grey", width=0.8),
            showlegend=False, hoverinfo="skip",
        ),
        row=1, col=2,
    )
    fig.add_trace(
        go.Scatter(
            x=[x_lo, x_hi], y=[med_yield, med_yield],
            mode="lines",
            line=dict(dash="dash", color="grey", width=0.8),
            showlegend=False, hoverinfo="skip",
        ),
        row=1, col=2,
    )

    # ── Panel B: quadrant annotations ─────────────────────────────────────────
    x_pad = (x_hi - x_lo) * 0.02
    y_pad = (y_hi - y_lo) * 0.02
    fig.add_annotation(
        x=x_hi - x_pad, y=y_hi - y_pad,
        text="<i>High yield<br>Low risk</i>",
        showarrow=False, font=dict(color="grey", size=9),
        xref="x2", yref="y2", xanchor="right", yanchor="top",
    )
    fig.add_annotation(
        x=x_lo + x_pad, y=y_lo + y_pad,
        text="<i>Low yield<br>High risk</i>",
        showarrow=False, font=dict(color="grey", size=9),
        xref="x2", yref="y2", xanchor="left", yanchor="bottom",
    )

    # ── Panel B: top treatment labels ─────────────────────────────────────────
    x_nudge = (x_hi - x_lo) * 0.02
    y_nudge = (y_hi - y_lo) * 0.03
    for _, row in top_df.iterrows():
        fig.add_annotation(
            x=row["CVaR_20"] + x_nudge,
            y=row["mean_yield"] + y_nudge,
            text=f"<b>{row['top_label']}</b><br>{row['trt_label']}",
            showarrow=False,
            font=dict(color=HIGHLIGHT_COLORS["top"], size=9),
            xref="x2", yref="y2",
            align="left",
            xanchor="left",
        )

    # ── Axes ──────────────────────────────────────────────────────────────────
    fig.update_yaxes(
        categoryorder="array",
        categoryarray=category_order,
        row=1, col=1,
    )
    fig.update_xaxes(
        tickformat=".0%",
        title_text="P(best) — proportion of years ranked #1",
        row=1, col=1,
    )
    fig.update_xaxes(
        title_text="CVaR₂₀ — mean yield in worst 20% of years (bu/acre)",
        row=1, col=2,
    )
    fig.update_yaxes(title_text="Mean yield (bu/acre)", row=1, col=2)

    # ── Layout ────────────────────────────────────────────────────────────────
    fig.update_layout(
        title=dict(
            text=(
                f"<b>Soybean management recommendation</b><br>"
                f"<span style='font-size:{SUBTITLE_FONT_SIZE}px; color:grey;'>"
                f"Site: {site}  |  Planting: {plt_dtDoy}  |  Scenario: {moisture_label}"
                f"</span>"
            ),
            font=dict(size=TITLE_FONT_SIZE),
        ),
        font=dict(size=BASE_FONT_SIZE),
        width=FIGURE_WIDTH,
        height=FIGURE_HEIGHT,
        legend=dict(orientation="h", y=-0.15),
        plot_bgcolor="white",
        paper_bgcolor="white",
    )
    fig.update_xaxes(showgrid=True, gridcolor="rgba(0,0,0,0.06)")
    fig.update_yaxes(showgrid=True, gridcolor="rgba(0,0,0,0.06)")

    return fig
