import time

import pytest

from src.data.grid import KDTreeGrid, build_grid, _parse_site
from src.data.loader import SummaryDataset
import pandas as pd


SITES = [
    "36.169701_-89.675003",
    "37.169701_-94.425003",
    "38.951701_-92.328003",  # near Columbia, MO
    "39.099724_-94.578560",  # near Kansas City
    "38.627003_-90.199402",  # near St. Louis
]


def _make_dataset(sites: list[str]) -> SummaryDataset:
    rows = [
        {
            "site": s,
            "plt_dtDoy": "Apr-15",
            "trt": "3.9_90000_15",
            "moisture_group": "all",
            "P_best": 0.1,
            "P_top3": 0.3,
            "CVaR_20": 50.0,
            "composite": 0.6,
            "q10_yield": 40.0,
            "q25_yield": 50.0,
            "q75_yield": 70.0,
            "q90_yield": 80.0,
        }
        for s in sites
    ]
    df = pd.DataFrame(rows).set_index(["site", "plt_dtDoy", "moisture_group"])
    return SummaryDataset(df=df, sites=sorted(sites))


def test_exact_coordinate_match():
    ds = _make_dataset(SITES)
    grid = build_grid(ds)
    for site in SITES:
        lat, lon = _parse_site(site)
        assert grid.nearest_site(lat, lon) == site


def test_off_grid_returns_closest():
    ds = _make_dataset(SITES)
    grid = build_grid(ds)
    # Slightly off Columbia → still resolves to Columbia site
    result = grid.nearest_site(38.95, -92.33)
    assert result == "38.951701_-92.328003"


def test_columbia_within_half_degree():
    ds = _make_dataset(SITES)
    grid = build_grid(ds)
    columbia_lat, columbia_lon = 38.9517, -92.3341
    result = grid.nearest_site(columbia_lat, columbia_lon)
    lat, lon = _parse_site(result)
    assert abs(lat - columbia_lat) <= 0.5
    assert abs(lon - columbia_lon) <= 0.5


def test_lookup_speed():
    ds = _make_dataset(SITES)
    grid = build_grid(ds)
    start = time.perf_counter()
    for _ in range(1000):
        grid.nearest_site(38.9517, -92.3341)
    elapsed_ms = (time.perf_counter() - start) * 1000
    # 1000 lookups well under 1000 ms → each under 1 ms
    assert elapsed_ms < 1000, f"1000 lookups took {elapsed_ms:.1f} ms"


def test_no_hardcoded_sites():
    import inspect
    import src.data.grid as grid_module
    source = inspect.getsource(grid_module)
    # Site strings contain lat_lon pattern like "38.951_-92.328"
    import re
    hardcoded = re.findall(r'"\d+\.\d+_-\d+\.\d+"', source)
    assert hardcoded == [], f"Hardcoded site strings found: {hardcoded}"
