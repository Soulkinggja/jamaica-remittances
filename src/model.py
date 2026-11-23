"""Shared data loading and forecasting models for the Jamaica remittances project."""
from pathlib import Path
import warnings

import numpy as np
import pandas as pd
from statsmodels.tsa.holtwinters import ExponentialSmoothing
from statsmodels.tsa.statespace.sarimax import SARIMAX

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"

CORRIDORS = ["united_states", "united_kingdom", "canada", "cayman_islands"]
WEST = ["hanover", "westmoreland", "st_james", "st_elizabeth", "trelawny"]


def _monthly(df):
    df.index = pd.PeriodIndex(df.index, freq="M")
    return df


def load_corridors():
    """Inbound remittances by source country, USD millions, Jan 2012 onward."""
    d = pd.read_csv(RAW / "boj_inbound_by_corridor.csv", index_col="month")
    d = _monthly(d)
    named = CORRIDORS + ["other_remittances"]
    d["other_countries"] = (d["total_remittances"] - d[named].sum(axis=1)).round(2)
    return d


def load_parishes():
    """Inbound remittances through remittance companies by parish, Jul 2020 onward.

    From 2024 BOJ reports Kingston and St. Andrew together, so both are merged
    for every month to keep the series consistent.
    """
    d = pd.read_csv(RAW / "boj_inbound_by_parish.csv", index_col="month")
    d = _monthly(d)
    d["kingston_st_andrew"] = d["kingston"].fillna(0) + d["st_andrew"].fillna(0)
    return d.drop(columns=["kingston", "st_andrew"])


def load_outflows():
    d = pd.read_csv(RAW / "boj_outbound_by_country.csv", index_col="month")
    return _monthly(d)


def load_counts():
    """Number of inbound transfers, thousands."""
    d = pd.read_csv(RAW / "boj_transfer_counts.csv", index_col="month")
    return _monthly(d)


# Forecasting models. All work on log values so seasonal swings scale with the level.

def seasonal_naive(y, h):
    """Next year looks like the same month last year."""
    last = y.iloc[-12:].values
    return np.array([last[i % 12] for i in range(h)])


def seasonal_naive_drift(y, h):
    """Same month last year, scaled by the last 12 months' growth."""
    growth = y.iloc[-12:].sum() / y.iloc[-24:-12].sum()
    base = seasonal_naive(y, h)
    return base * np.array([growth ** (1 + i // 12) for i in range(h)])


def ets(y, h):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        m = ExponentialSmoothing(np.log(y.values), trend="add", damped_trend=True,
                                 seasonal="add", seasonal_periods=12).fit()
    return np.exp(m.forecast(h))


def sarima_fit(y):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return SARIMAX(np.log(y.values), order=(1, 1, 1), seasonal_order=(0, 1, 1, 12)).fit(disp=False)


def sarima(y, h):
    return np.exp(sarima_fit(y).forecast(h))


MODELS = {
    "Seasonal naive": seasonal_naive,
    "Seasonal naive with growth": seasonal_naive_drift,
    "Exponential smoothing": ets,
    "SARIMA": sarima,
}
