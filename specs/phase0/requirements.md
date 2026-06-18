# Phase 0 — Data Layer: Requirements

## Functional Requirements

### FR-1: Dataset Loading
- Load `ExampleData_aggregate.csv` from a configurable path at application startup.
- Validate that all required columns are present: `site`, `plt_dtDoy`, `trt`, `moisture_group`, `P_best`, `P_top3`, `CVaR_20`, `composite`, and yield quantiles `q10_yield`, `q25_yield`, `q75_yield`, `q90_yield`.
- Raise a clear, descriptive error if the file is missing or a required column is absent.
- Expose the loaded data through a typed `SummaryDataset` wrapper that other modules import.

### FR-2: Grid Nearest-Neighbour Lookup
- Parse the `site` column (format: `"<lat>_<lon>"`, e.g. `"39.419701_-92.425003"`) to extract all unique (lat, lon) coordinate pairs.
- Build a KD-tree over those coordinates at startup (once, not per query).
- Expose `nearest_site(lat: float, lon: float) -> str` that returns the `site` string of the closest grid point.
- Lookup must complete in under 1 ms on the full Missouri grid.

### FR-3: Geocoding
- Accept free-text location input in any of these forms: county name (e.g. "Audrain County, MO"), city name (e.g. "Columbia, MO"), ZIP code (e.g. "65201"), street address.
- Return a (lat, lon) float tuple.
- Primary backend: Nominatim via `geopy` (no API key required).
- Fallback backend: Photon via `geopy` (OpenStreetMap-backed, no API key required). Note: `geopy.geocoders.USCensus` does not exist in geopy ≥ 2.x; Photon is used instead.
- Cache results in an in-memory dict keyed by normalised query string to avoid duplicate API calls within a session.
- Raise a descriptive `GeocodingError` if both backends fail.

### FR-4: Combined Location Resolution
- Provide a single `resolve_location(query: str) -> str` function that chains geocoding → nearest-site lookup and returns a `site` string.
- This is the primary entry point used by the agent in later phases.

---

## Non-Functional Requirements

- All three modules (`loader.py`, `grid.py`, `geocoder.py`) must be importable independently with no side effects at import time.
- Dataset loading is the only I/O that happens at startup; geocoding calls happen only when a query arrives.
- No hardcoded site strings or coordinates; all grid points are derived dynamically from the loaded DataFrame.
- Nominatim rate limit (1 req/s) must be respected; add a `time.sleep(1)` between sequential geocoding calls in tests and batch use.

---

## Module Interface Contract

```python
# src/data/loader.py
class SummaryDataset:
    df: pd.DataFrame          # full aggregate DataFrame
    sites: list[str]          # unique site strings

def load_dataset(path: str | Path) -> SummaryDataset: ...

# src/data/grid.py
def build_grid(dataset: SummaryDataset) -> KDTreeGrid: ...

class KDTreeGrid:
    def nearest_site(self, lat: float, lon: float) -> str: ...

# src/geo/geocoder.py
class GeocodingError(Exception): ...

def geocode(query: str) -> tuple[float, float]: ...          # (lat, lon)
def resolve_location(query: str, grid: KDTreeGrid) -> str:  # site string
    ...
```
