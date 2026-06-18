import pandas as pd
import pytest

from src.data.loader import REQUIRED_COLUMNS, SummaryDataset, load_dataset


@pytest.fixture
def aggregate_csv(tmp_path):
    cols = REQUIRED_COLUMNS + ["env", "trt"]
    rows = [
        {
            "env": "37.0_-92.0_74",
            "site": "37.0_-92.0",
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
        },
        {
            "env": "38.0_-93.0_74",
            "site": "38.0_-93.0",
            "plt_dtDoy": "May-01",
            "trt": "4.2_120000_30",
            "moisture_group": "dry",
            "P_best": 0.2,
            "P_top3": 0.4,
            "CVaR_20": 55.0,
            "composite": 0.7,
            "q10_yield": 42.0,
            "q25_yield": 52.0,
            "q75_yield": 72.0,
            "q90_yield": 82.0,
        },
    ]
    path = tmp_path / "aggregate.csv"
    pd.DataFrame(rows).to_csv(path, index=False)
    return path


def test_load_success(aggregate_csv):
    ds = load_dataset(aggregate_csv)
    assert isinstance(ds, SummaryDataset)
    assert len(ds.df) == 2
    assert ds.sites == ["37.0_-92.0", "38.0_-93.0"]


def test_multiindex_set(aggregate_csv):
    ds = load_dataset(aggregate_csv)
    assert ds.df.index.names == ["site", "plt_dtDoy", "moisture_group"]


def test_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_dataset(tmp_path / "nonexistent.csv")


def test_missing_column(tmp_path):
    path = tmp_path / "bad.csv"
    pd.DataFrame({"site": ["37.0_-92.0"], "plt_dtDoy": ["Apr-15"]}).to_csv(path, index=False)
    with pytest.raises(ValueError, match="missing required columns"):
        load_dataset(path)


def test_sites_nonempty(aggregate_csv):
    ds = load_dataset(aggregate_csv)
    assert len(ds.sites) > 0
