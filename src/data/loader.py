from __future__ import annotations

import dataclasses
from pathlib import Path

import pandas as pd

REQUIRED_COLUMNS = [
    "site",
    "plt_dtDoy",
    "trt",
    "moisture_group",
    "P_best",
    "P_top3",
    "CVaR_20",
    "composite",
    "q10_yield",
    "q25_yield",
    "q75_yield",
    "q90_yield",
]


@dataclasses.dataclass
class SummaryDataset:
    df: pd.DataFrame
    sites: list[str]


def load_dataset(path: str | Path) -> SummaryDataset:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Aggregate dataset not found: {path}")

    df = pd.read_csv(path)

    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"Aggregate CSV is missing required columns: {missing}")

    df = df.set_index(["site", "plt_dtDoy", "moisture_group"])

    sites = sorted(df.index.get_level_values("site").unique().tolist())
    return SummaryDataset(df=df, sites=sites)
