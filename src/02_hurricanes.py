"""How did remittances respond to Hurricane Beryl (July 2024) and Hurricane Melissa (October 2025)?

Part 1, national and by source country: fit exponential smoothing on data up to the
month before landfall, forecast the next six months, and compare with what arrived.
The gap is the excess (or shortfall) relative to a no storm path. A placebo check
runs the same test at every non storm month from 2022 onward to show how big a gap
normally is.

Part 2, by parish: a difference in differences on log remittances. The five western
parishes hit hardest by Melissa (Hanover, Westmoreland, St. James, St. Elizabeth,
Trelawny) are compared with the other parishes, month by month around landfall,
with parish and month effects.
"""
import json
import warnings

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

from model import ROOT, WEST, ets, load_corridors, load_counts, load_parishes

OUT = ROOT / "outputs"
d = load_corridors()
counts = load_counts()
STORMS = {"Beryl": "2024-07", "Melissa": "2025-10"}
SERIES = ["total_remittances", "united_states", "united_kingdom", "canada", "cayman_islands"]


def gap(series, landfall, h=6):
    lf = pd.Period(landfall, "M")
    train = series.loc[:lf - 1]
    actual = series.loc[lf:lf + h - 1]
    fc = ets(train, len(actual))
    return pd.DataFrame({"actual": actual.values, "expected": fc.round(2)}, index=actual.index.astype(str))


results, monthly = {}, []
for storm, lf in STORMS.items():
    for col in SERIES:
        g = gap(d[col], lf)
        g["gap"] = (g.actual - g.expected).round(2)
        g["gap_pct"] = (g.gap / g.expected * 100).round(1)
        for m, r in g.iterrows():
            monthly.append({"storm": storm, "series": col, "month": m, **r.to_dict()})
        results[f"{storm}|{col}"] = {
            "landfall_month_gap_pct": float(g.gap_pct.iloc[0]),
            "six_month_gap_usd_m": round(float(g.gap.sum()), 1),
            "six_month_gap_pct": round(float(g.gap.sum() / g.expected.sum() * 100), 1),
        }
pd.DataFrame(monthly).to_csv(OUT / "storm_gaps.csv", index=False)

# Placebo: one month ahead gaps at every non storm month, to calibrate what a
# normal surprise looks like.
y = d["total_remittances"]
skip = {pd.Period(m, "M") + k for m in STORMS.values() for k in range(6)} | \
       {pd.Period(f"2020-{m:02d}", "M") for m in range(3, 13)}
plac = []
for o in y.index:
    if o < pd.Period("2022-01", "M") or o in skip or o >= y.index[-1]:
        continue
    fc = ets(y.loc[:o - 1], 1)[0]
    plac.append((y.loc[o] / fc - 1) * 100)
plac = np.array(plac)
placebo = {"n": int(len(plac)), "mean_abs_gap_pct": round(float(np.abs(plac).mean()), 2),
           "p95_abs_gap_pct": round(float(np.percentile(np.abs(plac), 95)), 2),
           "max_gap_pct": round(float(plac.max()), 2), "min_gap_pct": round(float(plac.min()), 2)}

# Transfers: count and average size around Melissa, vs same month a year earlier.
avg = d["total_remittances"] * 1000 / counts["total"]
tr = {}
for m in ["2025-10", "2025-11", "2025-12"]:
    p = pd.Period(m, "M")
    tr[m] = {"count_yoy_pct": round(float((counts.total[p] / counts.total[p - 12] - 1) * 100), 1),
             "avg_size_usd": round(float(avg[p]), 0),
             "avg_size_yoy_pct": round(float((avg[p] / avg[p - 12] - 1) * 100), 1)}

# Part 2: parish difference in differences around Melissa.
p = load_parishes().drop(columns="total_remittances")
long = p.stack().rename("usd").reset_index()
long.columns = ["month", "parish", "usd"]
long = long[long.month >= pd.Period("2022-01", "M")]
long["west"] = long.parish.isin(WEST).astype(int)
long["log_usd"] = np.log(long.usd)
long["mstr"] = long.month.astype(str)
event = ["2025-09", "2025-10", "2025-11", "2025-12", "2026-01", "2026-02", "2026-03"]
for m in event:
    long[f"w_{m.replace('-', '_')}"] = ((long.mstr == m) & (long.west == 1)).astype(int)
# Jan and Feb 2026 parish figures repeat for several parishes (likely a BOJ carry
# forward), so they are kept but flagged in the README.
terms = " + ".join(f"w_{m.replace('-', '_')}" for m in event)
with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    fit = smf.ols(f"log_usd ~ C(parish) + C(mstr) + {terms}", data=long).fit(
        cov_type="cluster", cov_kwds={"groups": long.parish})
did = {}
for m in event:
    k = f"w_{m.replace('-', '_')}"
    did[m] = {"west_vs_rest_pct": round(float((np.exp(fit.params[k]) - 1) * 100), 1),
              "p_value": round(float(fit.pvalues[k]), 3)}

# Simple shares for the write up.
nov = load_parishes().loc[pd.Period("2025-11", "M")]
nov_prev = load_parishes().loc[pd.Period("2024-11", "M")]
growth_nov = ((nov / nov_prev - 1) * 100).round(1).drop("total_remittances").sort_values()

summary = {"storms": results, "placebo_one_month": placebo, "transfers": tr,
           "parish_did_west_vs_rest": did, "parish_yoy_nov_2025": growth_nov.to_dict()}
(OUT / "storm_summary.json").write_text(json.dumps(summary, indent=1))
print(json.dumps(summary, indent=1))
