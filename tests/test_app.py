import itertools
from datetime import datetime
from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest

import gradio as gr

from src.app.state import (
    KNOWN_CLOUD_MODELS,
    SessionState,
    clear_session,
    doy_sort_key,
    list_ollama_models,
    make_session_state,
)
from src.app.app import (
    _augment_query,
    _DATE_CHOICES,
    _resolve_model_str,
    _update_provider_visibility,
    build_app,
    _ctx,
    _ds,
)
from config import LLM_MODEL

# ── state.py — offline tests ──────────────────────────────────────────────────

def test_make_session_state():
    s = make_session_state()
    assert isinstance(s, SessionState)
    assert s.messages == []
    assert s.chat_history == []
    assert s.last_site is None


def test_clear_session_returns_fresh():
    s = make_session_state()
    s.messages.append({"role": "user", "content": "hello"})
    s.last_site = "39.0_-92.0"
    fresh = clear_session(s)
    assert fresh.messages == []
    assert fresh.last_site is None


def test_clear_session_does_not_mutate_argument():
    s = make_session_state()
    s.last_site = "39.0_-92.0"
    clear_session(s)
    assert s.last_site == "39.0_-92.0"


def test_list_ollama_models_no_server(monkeypatch):
    import requests as req
    monkeypatch.setattr(req, "get", lambda *a, **kw: (_ for _ in ()).throw(ConnectionError("no server")))
    result = list_ollama_models()
    assert result == []


def test_list_ollama_models_with_server(monkeypatch):
    import requests as req
    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = {
        "models": [{"name": "qwen2.5:14b"}, {"name": "llama3.1:8b"}]
    }
    monkeypatch.setattr(req, "get", lambda *a, **kw: mock_resp)
    result = list_ollama_models()
    assert result == ["llama3.1:8b", "qwen2.5:14b"]


def test_list_ollama_models_timeout(monkeypatch):
    import requests as req
    monkeypatch.setattr(req, "get", lambda *a, **kw: (_ for _ in ()).throw(req.exceptions.Timeout()))
    result = list_ollama_models()
    assert result == []


def test_doy_sort_key_type():
    result = doy_sort_key("Apr-15")
    assert isinstance(result, datetime)


def test_doy_sort_key_ordering():
    assert doy_sort_key("Mar-15") < doy_sort_key("Apr-01")
    assert doy_sort_key("Apr-01") < doy_sort_key("May-15")


def test_known_cloud_models_format():
    assert len(KNOWN_CLOUD_MODELS) >= 3
    for m in KNOWN_CLOUD_MODELS:
        assert "/" in m, f"Expected 'provider/model' format, got {m!r}"


def test_known_cloud_models_contains_claude():
    assert any("claude" in m for m in KNOWN_CLOUD_MODELS)


# ── app.py — _resolve_model_str ───────────────────────────────────────────────

def test_resolve_model_ollama():
    result = _resolve_model_str("Ollama (local)", "qwen2.5:14b", None, None)
    assert result == "ollama/qwen2.5:14b"


def test_resolve_model_ollama_empty_falls_back():
    result = _resolve_model_str("Ollama (local)", None, None, None)
    assert result == LLM_MODEL


def test_resolve_model_ollama_blank_falls_back():
    result = _resolve_model_str("Ollama (local)", "  ", None, None)
    assert result == LLM_MODEL


def test_resolve_model_claude():
    result = _resolve_model_str("Claude API", None, "anthropic/claude-sonnet-4-6", None)
    assert result == "anthropic/claude-sonnet-4-6"


def test_resolve_model_openai():
    result = _resolve_model_str("OpenAI", None, "openai/gpt-4o", None)
    assert result == "openai/gpt-4o"


def test_resolve_model_custom():
    result = _resolve_model_str("Custom", None, None, "ollama/llama3.1:8b")
    assert result == "ollama/llama3.1:8b"


# ── app.py — _augment_query ───────────────────────────────────────────────────

def test_augment_query_no_overlap():
    q = "Best management for Audrain County"
    result = _augment_query(q, "Apr-15", "dry", 3)
    assert "Apr-15" in result
    assert "dry" in result
    assert "3" in result


def test_augment_query_has_date_no_hint():
    q = "Management for Audrain County planted Apr-15"
    result = _augment_query(q, "Apr-15", "all", 3)
    assert result == q


def test_augment_query_has_moisture_no_hint():
    q = "Best in a dry year for Boone County"
    result = _augment_query(q, "Apr-15", "dry", 3)
    assert result == q


# ── app.py — _update_provider_visibility ─────────────────────────────────────

def test_update_visibility_ollama():
    updates = _update_provider_visibility("Ollama (local)")
    visible_flags = [u["visible"] for u in updates]
    # ollama_dd, refresh_btn visible; cloud_dd, api_key_box, custom_model_box hidden
    assert visible_flags == [True, True, False, False, False]


def test_update_visibility_claude():
    updates = _update_provider_visibility("Claude API")
    visible_flags = [u["visible"] for u in updates]
    assert visible_flags == [False, False, True, True, False]


def test_update_visibility_custom():
    updates = _update_provider_visibility("Custom")
    visible_flags = [u["visible"] for u in updates]
    assert visible_flags == [False, False, False, False, True]


# ── app.py — startup singletons and build_app ─────────────────────────────────

def test_ds_populated():
    assert len(_ds.sites) > 0


def test_ctx_dataset():
    assert _ctx.dataset is _ds


def test_date_choices_chronological():
    assert _DATE_CHOICES == sorted(_DATE_CHOICES, key=doy_sort_key)


def test_build_app_returns_blocks():
    app = build_app()
    assert isinstance(app, gr.Blocks)


def test_build_app_title():
    app = build_app()
    assert app.title == "Yield AI Assistant"


# ── agent.py — prior_messages parameter ──────────────────────────────────────

def _make_mock_completion(content: str = "No tools needed."):
    mock_response = MagicMock()
    mock_response.choices[0].message.tool_calls = None
    mock_response.choices[0].message.content = content
    return mock_response


@pytest.fixture(scope="module")
def _agent_tool_ctx():
    from src.data.loader import SummaryDataset
    from src.data.grid import build_grid
    from src.agent.tools import ToolContext

    rng = np.random.default_rng(99)
    sites = ["39.0_-92.0", "38.0_-93.0"]
    rows = []
    for site in sites:
        for date in ["Apr-15", "May-01"]:
            for moisture in ["dry", "all", "wet"]:
                for trt, mg, pop, rs in [
                    ("3.9_90000_15", 3.9, 90000, 15),
                    ("4.2_120000_30", 4.2, 120000, 30),
                ]:
                    p = float(rng.uniform(0.05, 0.30))
                    y = float(rng.uniform(50, 100))
                    rows.append({
                        "site": site, "plt_dtDoy": date, "moisture_group": moisture,
                        "trt": trt, "MG": mg, "pop": pop, "rs": rs,
                        "P_best": p, "P_best_lo": max(0.0, p - 0.05),
                        "P_best_hi": min(1.0, p + 0.05),
                        "P_top3": min(p * 3, 1.0),
                        "CVaR_20": float(rng.uniform(20, 60)),
                        "composite": float(rng.uniform(0.3, 0.9)),
                        "mean_yield": y, "med_yield": y * 0.98,
                        "q10_yield": y * 0.80, "q25_yield": y * 0.90,
                        "q75_yield": y * 1.10, "q90_yield": y * 1.20,
                    })
    df = pd.DataFrame(rows).set_index(["site", "plt_dtDoy", "moisture_group"])
    ds = SummaryDataset(df=df, sites=sorted(set(r["site"] for r in rows)))
    return ToolContext(dataset=ds, grid=build_grid(ds))


def test_run_agent_prior_messages_empty(monkeypatch, _agent_tool_ctx):
    import litellm
    from src.agent.agent import run_agent

    monkeypatch.setattr(litellm, "completion", lambda **kw: _make_mock_completion())
    resp = run_agent("Hello", _agent_tool_ctx, prior_messages=[])
    assert resp.text == "No tools needed."


def test_run_agent_prior_messages_inserted(monkeypatch, _agent_tool_ctx):
    import litellm
    from src.agent.agent import run_agent

    captured = {}

    def mock_completion(**kw):
        captured["messages"] = kw.get("messages", [])
        return _make_mock_completion()

    monkeypatch.setattr(litellm, "completion", mock_completion)

    prior = [
        {"role": "user", "content": "Previous question"},
        {"role": "assistant", "content": "Previous answer"},
    ]
    run_agent("New question", _agent_tool_ctx, prior_messages=prior)

    roles = [m["role"] for m in captured["messages"]]
    contents = [m.get("content", "") for m in captured["messages"]]

    assert roles[0] == "system"
    assert "Previous question" in contents
    assert "Previous answer" in contents
    assert contents[-1] == "New question"
