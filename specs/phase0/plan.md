# Phase 0 — Data Layer: Implementation Plan

## Overview

Build the foundational data layer: load the aggregate dataset, expose a typed wrapper, and resolve any free-text Missouri location to the nearest grid point. No agent, no plots — just clean, tested data access that all later phases depend on.

---

## Step 1: Project Scaffolding

Create the directory structure and conda environment file.

```
yield-ai-assistant/
  src/
    __init__.py
    data/
      __init__.py
      loader.py
      grid.py
    geo/
      __init__.py
      geocoder.py
  tests/
    __init__.py
    test_loader.py
    test_grid.py
    test_geocoder.py
  environment.yml
  config.py
```

`environment.yml` pins: `python=3.11`, `pandas`, `scipy`, `geopy`, `pytest`.

---

## Step 2: `src/data/loader.py`

1. Define `REQUIRED_COLUMNS` as a module-level constant listing all mandatory column names.
2. Implement `load_dataset(path)`:
   - Read CSV with `pd.read_csv`.
   - Check all required columns are present; raise `ValueError` with the missing column names if not.
   - Set a `MultiIndex` on `(site, plt_dtDoy, moisture_group)` for fast downstream lookups.
   - Return a `SummaryDataset(df=df, sites=sorted(df['site'].unique().tolist()))`.
3. `SummaryDataset` is a `dataclasses.dataclass` (or simple class) — no Pydantic dependency.

---

## Step 3: `src/data/grid.py`

1. `build_grid(dataset)`:
   - Parse each site string (`"lat_lon"`) into float pairs.
   - Stack into a numpy array; build `scipy.spatial.KDTree`.
   - Store the ordered list of site strings alongside the tree.
2. `KDTreeGrid.nearest_site(lat, lon)`:
   - Call `tree.query([lat, lon])` → index → return `sites[index]`.
   - No branching; the KD-tree handles all edge cases.

---

## Step 4: `src/geo/geocoder.py`

1. Module-level `_cache: dict[str, tuple[float, float]] = {}`.
2. `_normalise(query)`: lowercase, strip whitespace, collapse internal spaces.
3. `geocode(query)`:
   - Check cache first; return immediately on hit.
   - Try Nominatim (`geopy.geocoders.Nominatim(user_agent="yield-ai-assistant")`).
   - On failure or `None` result, try Photon (`geopy.geocoders.Photon`). Note: `USCensus` is not available in geopy ≥ 2.x.
   - On both failing, raise `GeocodingError(query)`.
   - On success, store in cache and return `(lat, lon)`.
4. `resolve_location(query, grid)`: calls `geocode` then `grid.nearest_site`.

---

## Step 5: `config.py`

Single file at project root:

```python
import os
from pathlib import Path

DATA_DIR = Path(os.getenv("YIELD_DATA_DIR", "data/Data for Ali"))
AGGREGATE_CSV = DATA_DIR / "ExampleData_aggregate.csv"
LLM_MODEL = os.getenv("YIELD_LLM_MODEL", "ollama/qwen2.5:14b")
```

All modules import from `config` rather than hardcoding paths.

---

## Step 6: Tests

| Test file | Cases |
|---|---|
| `test_loader.py` | Loads successfully; raises on missing file; raises on missing column; MultiIndex is set. |
| `test_grid.py` | `nearest_site` returns the exact site for a coordinate that exists in the grid; returns the closest site for an off-grid coordinate; runs in < 1 ms (use `time.perf_counter`). |
| `test_geocoder.py` | Round-trip for 5 Missouri cities: Columbia, Kansas City, St. Louis, Springfield, Joplin — returned (lat, lon) must be within 0.5° of known coordinates; cache hit avoids a second network call (mock the geocoder). |

Tests that hit Nominatim are marked `@pytest.mark.network` and skipped in CI unless the `NETWORK` env var is set.

---

## Step 7: Smoke Test

Add a `scripts/smoke_phase0.py` that:
1. Loads the dataset and prints row count and site count.
2. Builds the grid.
3. Resolves `"Columbia, MO"` → prints the returned site string.

Run manually to confirm end-to-end before marking the phase complete.

---

## Sequence Diagram

```
startup:
  load_dataset(AGGREGATE_CSV) → SummaryDataset
  build_grid(dataset)         → KDTreeGrid

query:
  resolve_location("Columbia, MO", grid)
    → geocode("columbia, mo")           # Nominatim
    → grid.nearest_site(38.95, -92.33)  # KD-tree
    → "38.951_-92.328"                  # site string
```
