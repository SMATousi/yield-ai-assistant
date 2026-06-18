import dataclasses
import itertools
import json

import numpy as np
import pandas as pd
import pytest
import plotly.graph_objects as go

from src.data.loader import SummaryDataset
from src.data.grid import build_grid
from src.agent.tools import (
    AgentError,
    ToolContext,
    ToolResult,
    TOOLS,
    execute_tool,
)
from src.agent.agent import AgentResponse, SYSTEM_PROMPT
from src.agent.interpreter import build_interpretation_prompt
from src.geo.geocoder import GeocodingError

# ── Synthetic dataset fixture ──────────────────────────────────────────────────

_SITES = ["39.0_-92.0", "38.0_-93.0"]
_DATES = ["Apr-15", "May-01"]
_MOISTURES = ["dry", "all", "wet"]
_TRTS = [
    {"trt": "3.9_90000_15",  "MG": 3.9, "pop": 90000,  "rs": 15},
    {"trt": "4.2_120000_30", "MG": 4.2, "pop": 120000, "rs": 30},
    {"trt": "4.5_150000_15", "MG": 4.5, "pop": 150000, "rs": 15},
]
_TEST_SITE = "39.0_-92.0"
_TEST_DATE = "Apr-15"
_TEST_MOISTURE = "all"
_MOCK_LAT, _MOCK_LON = 39.0, -92.0


@pytest.fixture(scope="module")
def synthetic_ds() -> SummaryDataset:
    rng = np.random.default_rng(7)
    rows = []
    for site, date, moisture, trt in itertools.product(_SITES, _DATES, _MOISTURES, _TRTS):
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
            "P_best_lo": max(0.0, p_best - 0.05),
            "P_best_hi": min(1.0, p_best + 0.05),
            "P_top3": min(p_best * 3, 1.0),
            "CVaR_20": cvar,
            "composite": composite,
            "mean_yield": mean_yield,
            "med_yield": mean_yield * 0.98,
            "q10_yield": mean_yield * 0.80,
            "q25_yield": mean_yield * 0.90,
            "q75_yield": mean_yield * 1.10,
            "q90_yield": mean_yield * 1.20,
        })
    df = pd.DataFrame(rows).set_index(["site", "plt_dtDoy", "moisture_group"])
    sites = sorted(df.index.get_level_values("site").unique().tolist())
    return SummaryDataset(df=df, sites=sites)


@pytest.fixture(scope="module")
def tool_ctx(synthetic_ds) -> ToolContext:
    grid = build_grid(synthetic_ds)
    return ToolContext(dataset=synthetic_ds, grid=grid)


# ── tools.py — dataclasses and TOOLS list ─────────────────────────────────────

def test_tool_context_construction(synthetic_ds):
    grid = build_grid(synthetic_ds)
    ctx = ToolContext(dataset=synthetic_ds, grid=grid)
    assert ctx.dataset is synthetic_ds
    assert ctx.grid is grid


def test_tools_list_length():
    assert len(TOOLS) == 3


def test_tools_list_structure():
    for entry in TOOLS:
        assert entry["type"] == "function"
        fn = entry["function"]
        assert "name" in fn
        assert "description" in fn
        assert "parameters" in fn


def test_tools_names():
    names = [t["function"]["name"] for t in TOOLS]
    assert names[0] == "lookup_nearest_site"
    assert names[1] == "generate_recommendation_plot"
    assert names[2] == "generate_doy_response_plot"


def test_moisture_scenario_enum_and_description():
    params = TOOLS[1]["function"]["parameters"]["properties"]
    assert "moisture_scenario" in params
    desc = params["moisture_scenario"]["description"]
    assert "dry" in desc and "all" in desc and "wet" in desc


def test_planting_date_not_required():
    required = TOOLS[1]["function"]["parameters"].get("required", [])
    assert "planting_date" not in required


# ── tools.py — execute_tool (offline, monkeypatched geocoder) ─────────────────

def test_execute_tool_lookup(tool_ctx, monkeypatch):
    monkeypatch.setattr("src.geo.geocoder.geocode", lambda q: (_MOCK_LAT, _MOCK_LON))
    result = execute_tool("lookup_nearest_site", {"location": "Columbia, MO"}, tool_ctx)
    assert isinstance(result, ToolResult)
    assert result.figure is None
    data = json.loads(result.content)
    assert "site" in data
    assert data["site"] == _TEST_SITE


def test_execute_tool_recommendation(tool_ctx, monkeypatch):
    monkeypatch.setattr("src.geo.geocoder.geocode", lambda q: (_MOCK_LAT, _MOCK_LON))
    result = execute_tool(
        "generate_recommendation_plot",
        {"location": "Test, MO", "planting_date": _TEST_DATE, "moisture_scenario": _TEST_MOISTURE},
        tool_ctx,
    )
    assert isinstance(result, ToolResult)
    assert result.figure is not None
    assert isinstance(result.figure, go.Figure)
    data = json.loads(result.content)
    assert data["site"] == _TEST_SITE
    assert "top_trt_label" in data


def test_execute_tool_recommendation_default_date(tool_ctx, monkeypatch):
    monkeypatch.setattr("src.geo.geocoder.geocode", lambda q: (_MOCK_LAT, _MOCK_LON))
    result = execute_tool(
        "generate_recommendation_plot",
        {"location": "Test, MO", "moisture_scenario": "dry"},
        tool_ctx,
    )
    assert result.figure is not None
    data = json.loads(result.content)
    assert data["plt_dtDoy"] == "Apr-15"


def test_execute_tool_doy(tool_ctx, monkeypatch):
    monkeypatch.setattr("src.geo.geocoder.geocode", lambda q: (_MOCK_LAT, _MOCK_LON))
    result = execute_tool("generate_doy_response_plot", {"location": "Test, MO"}, tool_ctx)
    assert isinstance(result, ToolResult)
    assert result.figure is not None
    assert isinstance(result.figure, go.Figure)


def test_execute_tool_unknown_raises(tool_ctx):
    with pytest.raises(AgentError):
        execute_tool("nonexistent_tool", {}, tool_ctx)


def test_execute_tool_geocoding_error_returns_content(tool_ctx, monkeypatch):
    def _fail(q: str):
        raise GeocodingError("bad location")

    monkeypatch.setattr("src.geo.geocoder.geocode", _fail)
    result = execute_tool("lookup_nearest_site", {"location": "Nowhere"}, tool_ctx)
    assert result.figure is None
    assert len(result.content) > 0
    assert "Error" in result.content


# ── agent.py — structure (no LLM call) ────────────────────────────────────────

def test_agent_response_fields():
    r = AgentResponse(text="hello", figure=None, site=None, raw_messages=[])
    assert r.text == "hello"
    assert r.figure is None
    assert r.site is None
    assert r.raw_messages == []


def test_system_prompt_not_empty():
    assert len(SYSTEM_PROMPT) > 0
    assert "MU Extension" in SYSTEM_PROMPT


# ── interpreter.py — offline unit tests ───────────────────────────────────────

def test_build_interpretation_prompt(synthetic_ds):
    prompt = build_interpretation_prompt(
        synthetic_ds.df, _TEST_SITE, _TEST_DATE, _TEST_MOISTURE
    )
    assert isinstance(prompt, str)
    assert "P(best)" in prompt
    assert "CVaR" in prompt
    assert "grid point" in prompt


def test_build_interpretation_prompt_word_count_instruction(synthetic_ds):
    prompt = build_interpretation_prompt(
        synthetic_ds.df, _TEST_SITE, _TEST_DATE, _TEST_MOISTURE
    )
    assert "≥150 words" in prompt


def test_build_interpretation_prompt_contains_top_trt(synthetic_ds):
    prompt = build_interpretation_prompt(
        synthetic_ds.df, _TEST_SITE, _TEST_DATE, _TEST_MOISTURE
    )
    flat = synthetic_ds.df.reset_index()
    top = (
        flat[
            (flat["site"] == _TEST_SITE)
            & (flat["plt_dtDoy"] == _TEST_DATE)
            & (flat["moisture_group"] == _TEST_MOISTURE)
        ]
        .sort_values("composite", ascending=False)
        .iloc[0]
    )
    expected_label = f"MG{top['MG']} · {top['pop'] / 1000:.0f}k · {top['rs']}in"
    assert expected_label in prompt


def test_build_interpretation_prompt_empty_raises(synthetic_ds):
    with pytest.raises(ValueError):
        build_interpretation_prompt(synthetic_ds.df, "nonexistent_site", "Apr-15", "dry")
