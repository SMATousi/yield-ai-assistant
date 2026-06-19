import pytest
from unittest.mock import MagicMock, patch

import src.geo.geocoder as geocoder_module
from src.geo.geocoder import GeocodingError, _normalise, geocode, resolve_location
from src.data.grid import KDTreeGrid, build_grid
from src.data.loader import SummaryDataset
import pandas as pd
import numpy as np


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

MISSOURI_CITIES = [
    ("Columbia, MO",     38.9517,  -92.3341),
    ("Kansas City, MO",  39.0997,  -94.5786),
    ("St. Louis, MO",    38.6270,  -90.1994),
    ("Springfield, MO",  37.2153,  -93.2982),
    ("Joplin, MO",       37.0842,  -94.5133),
]

SITES = [
    "36.169701_-89.675003",
    "37.169701_-94.425003",
    "38.951701_-92.328003",
    "39.099724_-94.578560",
    "38.627003_-90.199402",
    "37.215300_-93.298200",
    "37.084200_-94.513300",
]


def _make_grid(sites: list[str]) -> KDTreeGrid:
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
    ds = SummaryDataset(df=df, sites=sorted(sites))
    return build_grid(ds)


def _mock_location(lat: float, lon: float) -> MagicMock:
    loc = MagicMock()
    loc.latitude = lat
    loc.longitude = lon
    return loc


# ---------------------------------------------------------------------------
# Unit tests (no network)
# ---------------------------------------------------------------------------

def test_normalise():
    assert _normalise("  Columbia,  MO  ") == "columbia, mo"


def test_geocoding_error_raised():
    with patch.object(geocoder_module._nominatim, "geocode", return_value=None), \
         patch.object(geocoder_module._photon, "geocode", return_value=None):
        with pytest.raises(GeocodingError):
            geocode("completely invalid xyz 99999")


def test_cache_hit_skips_network():
    geocoder_module._cache.clear()
    fake_loc = _mock_location(38.9517, -92.3341)

    with patch.object(geocoder_module._nominatim, "geocode", return_value=fake_loc) as mock_nom:
        geocode("Columbia, MO")
        geocode("Columbia, MO")  # second call — should hit cache
        assert mock_nom.call_count == 1


def test_photon_fallback():
    geocoder_module._cache.clear()
    fake_loc = _mock_location(38.9517, -92.3341)

    with patch.object(geocoder_module._nominatim, "geocode", return_value=None), \
         patch.object(geocoder_module._photon, "geocode", return_value=fake_loc):
        lat, lon = geocode("some address only census knows")
        assert lat == pytest.approx(38.9517)
        assert lon == pytest.approx(-92.3341)


def test_resolve_location_returns_site_string():
    geocoder_module._cache.clear()
    grid = _make_grid(SITES)
    fake_loc = _mock_location(38.9517, -92.3341)

    with patch.object(geocoder_module._nominatim, "geocode", return_value=fake_loc):
        site = resolve_location("Columbia, MO", grid)
    assert "_" in site
    parts = site.split("_", 1)
    assert len(parts) == 2
    float(parts[0])   # lat is parseable
    float(parts[1])   # lon is parseable


# ---------------------------------------------------------------------------
# Network tests — run with: NETWORK=1 pytest -m network
# ---------------------------------------------------------------------------

@pytest.mark.network
@pytest.mark.parametrize("city, expected_lat, expected_lon", MISSOURI_CITIES)
def test_geocode_missouri_cities(city, expected_lat, expected_lon):
    geocoder_module._cache.clear()
    lat, lon = geocode(city)
    assert abs(lat - expected_lat) <= 0.5, f"{city}: lat {lat} too far from {expected_lat}"
    assert abs(lon - expected_lon) <= 0.5, f"{city}: lon {lon} too far from {expected_lon}"


@pytest.mark.network
@pytest.mark.parametrize("query", [
    "Audrain County, MO",
    "65201",
])
def test_resolve_location_network(query):
    import time
    geocoder_module._cache.clear()
    grid = _make_grid(SITES)
    time.sleep(1)  # respect Nominatim 1 req/s rate limit
    site = resolve_location(query, grid)
    assert "_" in site
    parts = site.split("_", 1)
    assert len(parts) == 2
    float(parts[0])  # lat parseable
    float(parts[1])  # lon parseable
