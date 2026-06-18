#!/usr/bin/env python3
"""Smoke test for Phase 1 — run from the project root."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import plotly.graph_objects as go

from config import AGGREGATE_CSV
from src.data.loader import load_dataset
from src.plots.recommendation import plot_recommendation
from src.plots.doy_response import plot_doy_response

SITE = "39.419701_-92.425003"

print("Loading dataset...")
ds = load_dataset(AGGREGATE_CSV)
print(f"  {len(ds.df):,} rows, {len(ds.sites)} unique sites")

assert SITE in ds.sites, f"Site {SITE!r} not found in dataset. Available: {ds.sites[:5]}"

print(f"\nRendering recommendation plot for {SITE} / Apr-15 / all...")
fig_rec = plot_recommendation(ds.df, SITE, "Apr-15", "all")
assert isinstance(fig_rec, go.Figure)
out_rec = Path("smoke_recommendation.html")
fig_rec.write_html(str(out_rec))
print(f"  Traces: {len(fig_rec.data)}  →  saved {out_rec}")

print(f"\nRendering DOY response plot for {SITE}...")
fig_doy = plot_doy_response(ds.df, SITE)
assert isinstance(fig_doy, go.Figure)
out_doy = Path("smoke_doy_response.html")
fig_doy.write_html(str(out_doy))
print(f"  Traces: {len(fig_doy.data)}  →  saved {out_doy}")

print("\nPhase 1 OK.")
