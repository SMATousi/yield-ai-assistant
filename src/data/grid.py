from __future__ import annotations

import numpy as np
from scipy.spatial import KDTree

from src.data.loader import SummaryDataset


class KDTreeGrid:
    def __init__(self, sites: list[str], coords: np.ndarray) -> None:
        self._sites = sites
        self._tree = KDTree(coords)

    def nearest_site(self, lat: float, lon: float) -> str:
        _, idx = self._tree.query([lat, lon])
        return self._sites[idx]


def build_grid(dataset: SummaryDataset) -> KDTreeGrid:
    sites = dataset.sites
    coords = np.array([_parse_site(s) for s in sites])
    return KDTreeGrid(sites=sites, coords=coords)


def _parse_site(site: str) -> tuple[float, float]:
    lat_str, lon_str = site.split("_", 1)
    return float(lat_str), float(lon_str)
