#!/usr/bin/env python3
"""
Smoke test for Phase 3 — GUI.

Verifies the app builds without error and startup singletons are populated.
Does NOT launch a browser or call an LLM.
Run from the project root.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import gradio as gr

from src.app.app import build_app, _ds, _ctx

assert len(_ds.sites) > 0, "Dataset must contain at least one site"
assert _ctx.dataset is _ds, "ToolContext must reference the loaded dataset"

app = build_app()
assert isinstance(app, gr.Blocks), f"Expected gr.Blocks, got {type(app)}"
assert app.title == "Yield AI Assistant"

print(f"App built. {len(_ds.sites)} sites, {len(_ds.df):,} rows.")
print("Phase 3 OK.")
