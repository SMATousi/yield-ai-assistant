#!/usr/bin/env python3
"""
Smoke test for Phase 2 — Agent Core.

Requires a running LLM. Set YIELD_LLM_MODEL to override the default:
    YIELD_LLM_MODEL=anthropic/claude-sonnet-4-6 python scripts/smoke_phase2.py

Default model: ollama/qwen2.5:14b (requires Ollama running locally).
Run from the project root.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import plotly.graph_objects as go

from config import AGGREGATE_CSV
from src.data.loader import load_dataset
from src.data.grid import build_grid
from src.agent.tools import ToolContext
from src.agent.agent import run_agent, AgentResponse

QUERY = "Show me the best soybean management for Audrain County in a dry spring"

print("Loading dataset...")
ds = load_dataset(AGGREGATE_CSV)
print(f"  {len(ds.df):,} rows, {len(ds.sites)} unique sites")

print("Building grid...")
grid = build_grid(ds)
ctx = ToolContext(dataset=ds, grid=grid)

print(f"\nRunning agent query: {QUERY!r}")
response: AgentResponse = run_agent(QUERY, ctx)

assert isinstance(response.figure, go.Figure), "Expected a go.Figure in the response"
assert response.site is not None, "Expected a resolved site string"
assert len(response.text) >= 150, f"Expected ≥150 chars of text, got {len(response.text)}"

out = Path("smoke_agent_recommendation.html")
response.figure.write_html(str(out))

print(f"  Resolved site: {response.site}")
print(f"  Text length: {len(response.text)} chars")
print(f"  Figure: {type(response.figure)}")
print(f"  Saved: {out}")
print("\nPhase 2 OK.")
