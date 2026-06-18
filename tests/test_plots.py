import itertools

import numpy as np
import pandas as pd
import pytest
import plotly.graph_objects as go

from src.plots.theme import mg_colors, fg_colors, make_trt_label
from src.plots.recommendation import plot_recommendation
from src.plots.doy_response import plot_doy_response, _get_date_order

# ── Synthetic dataset fixture ──────────────────────────────────────────────────

SITES = ["37.0_-92.0", "38.0_-93.0", "39.0_-94.0", "40.0_-91.0", "36.0_-90.0"]
# Deliberately out of alphabetical order to test date sorting
DATES = ["Mar-15", "Apr-01", "May-15"]
MOISTURES = ["dry", "all", "wet"]
TRTS = [
    {"trt": "3.9_90000_15",  "MG": 3.9, "pop": 90000,  "rs": 15},
    {"trt": "4.2_120000_30", "MG": 4.2, "pop": 120000, "rs": 30},
    {"trt": "4.5_150000_15", "MG": 4.5, "pop": 150000, "rs": 15},
    {"trt": "3.6_90000_30",  "MG": 3.6, "pop": 90000,  "rs": 30},
]
TEST_SITE = "39.0_-94.0"


@pytest.fixture(scope="module")
def synthetic_df() -> pd.DataFrame:
    rng = np.random.default_rng(42)
    rows = []
    for site, date, moisture, trt in itertools.product(SITES, DATES, MOISTURES, TRTS):
        p_best = float(rng.uniform(0.05, 0.30))
        mean_yield = float(rng.uniform(50, 100))
        cvar = float(rng.uniform(20, 60))
        composite = float(rng.uniform(0.3, 0.9))
        rows.append({
            "site": site,
            "plt_dtDoy": date,
            "moisture_group": moisture,
            "trt": trt["trt"],
            "MG": trt["MG"],
            "pop": trt["pop"],
            "rs": trt["rs"],
            "P_best": p_best,
            "P_top3": min(p_best * 3, 1.0),
            "CVaR_20": cvar,
            "composite": composite,
            "mean_yield": mean_yield,
            "med_yield": mean_yield * 0.98,
            "q10_yield": mean_yield * 0.80,
            "q25_yield": mean_yield * 0.90,
            "q75_yield": mean_yield * 1.10,
            "q90_yield": mean_yield * 1.20,
            "P_best_lo": max(0.0, p_best - 0.05),
            "P_best_hi": min(1.0, p_best + 0.05),
            "ci_width": 0.10,
        })
    return pd.DataFrame(rows).set_index(["site", "plt_dtDoy", "moisture_group"])


# ── theme tests ────────────────────────────────────────────────────────────────

def test_theme_no_side_effects():
    import importlib
    import src.plots.theme as t
    importlib.reload(t)  # reload verifies import has no side effects


def test_theme_mg_colors_deterministic():
    first = mg_colors(["3.9", "4.2", "4.5"])
    second = mg_colors(["3.9", "4.2", "4.5"])
    assert first == second


def test_theme_mg_colors_hex_values():
    result = mg_colors(["3.9", "4.2"])
    assert len(result) == 2
    for v in result.values():
        assert v.startswith("#"), f"Expected hex colour, got {v!r}"
        assert len(v) == 7


def test_theme_mg_colors_empty():
    assert mg_colors([]) == {}


# ── recommendation tests ───────────────────────────────────────────────────────

def test_recommendation_returns_figure(synthetic_df):
    fig = plot_recommendation(synthetic_df, TEST_SITE, "Apr-01", "all")
    assert isinstance(fig, go.Figure)


def test_recommendation_trace_count(synthetic_df):
    fig = plot_recommendation(synthetic_df, TEST_SITE, "Apr-01", "all")
    # At least 2 panel-A traces (other + top) and ≥1 panel-B trace (per MG)
    assert len(fig.data) >= 3


def test_recommendation_hover_template(synthetic_df):
    fig = plot_recommendation(synthetic_df, TEST_SITE, "Apr-01", "all")
    has_pbest_hover = any(
        trace.hovertemplate is not None and "P(best)" in trace.hovertemplate
        for trace in fig.data
    )
    assert has_pbest_hover


def test_recommendation_error_x_present(synthetic_df):
    fig = plot_recommendation(synthetic_df, TEST_SITE, "Apr-01", "all")
    has_error_x = any(
        hasattr(trace, "error_x")
        and trace.error_x is not None
        and trace.error_x.array is not None
        for trace in fig.data
    )
    assert has_error_x


def test_recommendation_empty_raises(synthetic_df):
    with pytest.raises(ValueError):
        plot_recommendation(synthetic_df, "nonexistent_site", "Apr-01", "all")


def test_recommendation_bad_date_raises(synthetic_df):
    with pytest.raises(ValueError):
        plot_recommendation(synthetic_df, TEST_SITE, "Jan-01", "all")


# ── doy response tests ────────────────────────────────────────────────────────

def test_doy_response_returns_figure(synthetic_df):
    fig = plot_doy_response(synthetic_df, TEST_SITE)
    assert isinstance(fig, go.Figure)


def test_doy_response_subplot_count(synthetic_df):
    fig = plot_doy_response(synthetic_df, TEST_SITE)
    # 3-row subplot → layout has yaxis, yaxis2, yaxis3
    assert hasattr(fig.layout, "yaxis3")


def test_doy_response_star_present(synthetic_df):
    fig = plot_doy_response(synthetic_df, TEST_SITE)
    has_star = any(
        hasattr(trace, "marker")
        and trace.marker is not None
        and trace.marker.symbol == "star"
        for trace in fig.data
    )
    assert has_star


def test_doy_response_x_order(synthetic_df):
    fig = plot_doy_response(synthetic_df, TEST_SITE)
    # Chronological order: Mar-15, Apr-01, May-15 — NOT alphabetical (Apr-01, Mar-15, May-15)
    expected = ("Mar-15", "Apr-01", "May-15")
    assert fig.layout.xaxis.categoryarray == expected


def test_doy_response_empty_raises(synthetic_df):
    with pytest.raises(ValueError):
        plot_doy_response(synthetic_df, "nonexistent_site")
