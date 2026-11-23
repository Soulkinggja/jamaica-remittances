"""Backtest four forecasting models on total remittances, then forecast to Dec 2027.

Rolling origin: for every month from Jan 2023 onward, fit on data up to that month
and forecast the next 12. Scores are mean absolute percentage error (MAPE) at a
one month horizon and for the next 12 months added together (the annual total).
"""
import json

import numpy as np
np.random.seed(7)
import pandas as pd

from model import MODELS, ROOT, load_corridors, sarima_fit

OUT = ROOT / "outputs"
OUT.mkdir(exist_ok=True)

d = load_corridors()
y = d["total_remittances"]

origins = [p for p in y.index if p >= pd.Period("2022-12", "M")]
rows = []
for o in origins:
    train = y.loc[:o]
    test = y.loc[o + 1:o + 12]
    if len(test) == 0:
        continue
    for name, f in MODELS.items():
        fc = f(train, len(test))
        rows.append({
            "origin": str(o), "model": name,
            "ape_1m": abs(fc[0] / test.iloc[0] - 1) * 100,
            "ape_12m_total": abs(fc.sum() / test.sum() - 1) * 100 if len(test) == 12 else np.nan,
            "target_month": str(test.index[0]),
        })
bt = pd.DataFrame(rows)
bt.to_csv(OUT / "backtest.csv", index=False)

storm = {"2024-07", "2025-10", "2025-11", "2025-12"}
score = bt.groupby("model").agg(mape_1m=("ape_1m", "mean"),
                                mape_12m_total=("ape_12m_total", "mean"),
                                n_1m=("ape_1m", "size"))
score["mape_1m_no_storms"] = bt[~bt.target_month.isin(storm)].groupby("model").ape_1m.mean()
score = score.round(2).sort_values("mape_1m")
print(score)
score.to_csv(OUT / "backtest_scores.csv")

# Forecast to Dec 2027 with the backtest winner, exponential smoothing on logs.
# Intervals come from 2,000 simulated future paths, so the annual range is a real
# 80 percent range for the year, not monthly bounds added together.
import warnings
from statsmodels.tsa.exponential_smoothing.ets import ETSModel

last = y.index[-1]
h = (pd.Period("2027-12", "M") - last).n
months = [last + i + 1 for i in range(h)]
fc_rows, annual = [], {}
for col in ["total_remittances", "united_states", "united_kingdom", "canada", "cayman_islands"]:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        fit = ETSModel(np.log(d[col].values), error="add", trend="add", damped_trend=True,
                       seasonal="add", seasonal_periods=12).fit(disp=False)
        sims = np.exp(fit.simulate(h, repetitions=2000, anchor="end"))
    mean = np.exp(fit.forecast(h))
    lo, hi = np.percentile(sims, [10, 90], axis=1)
    for i, m in enumerate(months):
        fc_rows.append({"month": str(m), "series": col, "forecast": round(mean[i], 2),
                        "low80": round(lo[i], 2), "high80": round(hi[i], 2)})
    if col == "total_remittances":
        idx26 = [i for i, m in enumerate(months) if m.year == 2026]
        idx27 = [i for i, m in enumerate(months) if m.year == 2027]
        done26 = d[col].loc["2026-01":].sum()
        a26 = done26 + sims[idx26].sum(axis=0)
        a27 = sims[idx27].sum(axis=0)
        annual = {
            "forecast_2026_total": round(done26 + mean[idx26].sum(), 1),
            "range80_2026": [round(x, 1) for x in np.percentile(a26, [10, 90])],
            "forecast_2027_total": round(mean[idx27].sum(), 1),
            "range80_2027": [round(x, 1) for x in np.percentile(a27, [10, 90])],
        }
fc = pd.DataFrame(fc_rows)
fc.to_csv(OUT / "forecast.csv", index=False)
summary = {"model": "Exponential smoothing (damped trend, log scale)", "last_actual_month": str(last),
           "actual_2024": round(y.loc["2024-01":"2024-12"].sum(), 1),
           "actual_2025": round(y.loc["2025-01":"2025-12"].sum(), 1), **annual}
print(json.dumps(summary, indent=1))
(OUT / "forecast_summary.json").write_text(json.dumps(summary, indent=1))
