# Phase 0 — Data Layer: Validation

## Gate Criterion (from Roadmap)

> Given "Columbia, MO", the system returns a site string whose lat/lon is within 0.5° of Columbia's true coordinates (38.9517° N, 92.3341° W).

This is the single pass/fail gate. All checklist items below must be green before Phase 1 begins.

---

## Checklist

### Dataset Loading

- [x] `load_dataset` returns a `SummaryDataset` without error on the real `ExampleData_aggregate.csv`.
- [x] `dataset.df` has a `MultiIndex` on `(site, plt_dtDoy, moisture_group)`.
- [x] `dataset.sites` is a non-empty list of strings in `"lat_lon"` format.
- [x] `load_dataset` raises `ValueError` (with a message naming the missing columns) when a required column is absent.
- [x] `load_dataset` raises `FileNotFoundError` when the path does not exist.

### Grid Lookup

- [x] `nearest_site(lat, lon)` returns the exact site string for a coordinate taken directly from the dataset.
- [x] `nearest_site(38.9517, -92.3341)` (Columbia, MO) returns a site whose parsed lat/lon is within 0.5° of (38.9517, -92.3341).
- [x] Lookup time is < 1 ms (asserted in `test_grid.py` via `time.perf_counter`).
- [x] No site strings are hardcoded anywhere in `grid.py`.

### Geocoding

- [ ] `geocode("Columbia, MO")` returns (lat, lon) within 0.5° of (38.9517, -92.3341). *(network test — verified manually)*
- [ ] `geocode("Kansas City, MO")` returns (lat, lon) within 0.5° of (39.0997, -94.5786). *(network test)*
- [ ] `geocode("St. Louis, MO")` returns (lat, lon) within 0.5° of (38.6270, -90.1994). *(network test)*
- [ ] `geocode("Springfield, MO")` returns (lat, lon) within 0.5° of (37.2153, -93.2982). *(network test)*
- [ ] `geocode("Joplin, MO")` returns (lat, lon) within 0.5° of (37.0842, -94.5133). *(network test)*
- [x] A second call with the same query (after mocking the geocoder) does not make a second network request (cache hit).
- [x] `geocode` raises `GeocodingError` when both Nominatim and Photon return `None`.

### Integration

- [x] `resolve_location("Columbia, MO", grid)` returns a site string (end-to-end, confirmed by smoke test).
- [ ] `resolve_location("Audrain County, MO", grid)` returns a site string without error. *(network test)*
- [ ] `resolve_location("65201", grid)` (Columbia ZIP) returns a site string without error. *(network test)*
- [x] `resolve_location("completely invalid xyz 99999", grid)` raises `GeocodingError`.

### Code Quality

- [x] All three modules are importable with no side effects (no file I/O, no network calls at import time).
- [x] `pytest` runs with zero failures and zero warnings (excluding network-marked tests when offline).
- [x] `scripts/smoke_phase0.py` runs to completion and prints a valid site string for "Columbia, MO".

---

## How to Run Validation

```bash
# Unit + integration tests (no network)
pytest tests/ -v -m "not network"

# Include live geocoding tests (requires internet)
NETWORK=1 pytest tests/ -v

# Smoke test
python scripts/smoke_phase0.py
```

Actual smoke output (2026-06-17):
```
Loading dataset...
  172,152 rows, 203 unique sites.
Building grid...
  KD-tree built over 203 points.
Resolving 'Columbia, MO'...
  → 38.919701_-92.425003  (distance: 0.096°)

Phase 0 OK.
```
