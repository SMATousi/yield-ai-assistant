#!/usr/bin/env python3
"""Smoke test for Phase 0 — run from the project root."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import AGGREGATE_CSV
from src.data.loader import load_dataset
from src.data.grid import build_grid, _parse_site
from src.geo.geocoder import resolve_location

print("Loading dataset...")
ds = load_dataset(AGGREGATE_CSV)
print(f"  {len(ds.df):,} rows, {len(ds.sites)} unique sites")

print("Building grid...")
grid = build_grid(ds)
print(f"  KD-tree built over {len(ds.sites)} points")

query = "Columbia, MO"
print(f"Resolving '{query}'...")
site = resolve_location(query, grid)
lat, lon = _parse_site(site)
columbia_lat, columbia_lon = 38.9517, -92.3341
dist = ((lat - columbia_lat) ** 2 + (lon - columbia_lon) ** 2) ** 0.5
print(f"  → {site}  (distance: {dist:.3f}°)")

assert dist <= 0.5, f"Site too far from Columbia: {dist:.3f}°"
print("\nPhase 0 OK.")
