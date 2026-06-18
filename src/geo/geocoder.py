from __future__ import annotations

import re

from geopy.geocoders import Nominatim, Photon

from src.data.grid import KDTreeGrid

_cache: dict[str, tuple[float, float]] = {}

_nominatim = Nominatim(user_agent="yield-ai-assistant")
_photon = Photon(user_agent="yield-ai-assistant")


class GeocodingError(Exception):
    pass


def _normalise(query: str) -> str:
    return re.sub(r"\s+", " ", query.strip().lower())


def geocode(query: str) -> tuple[float, float]:
    key = _normalise(query)
    if key in _cache:
        return _cache[key]

    location = _nominatim.geocode(query)
    if location is None:
        location = _photon.geocode(query)
    if location is None:
        raise GeocodingError(f"Could not geocode: {query!r}")

    result = (location.latitude, location.longitude)
    _cache[key] = result
    return result


def resolve_location(query: str, grid: KDTreeGrid) -> str:
    lat, lon = geocode(query)
    return grid.nearest_site(lat, lon)
