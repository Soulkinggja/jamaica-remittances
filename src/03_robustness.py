"""Robustness checks for the Hurricane Melissa results, plus the visitor comparison.

1. Parish damage intensity: replace the five western parishes dummy with each parish's
   damage as a share of its exposed value, from the World Bank GRADE report.
2. Wild cluster bootstrap: with only 13 parish clusters, clustered standard errors can
   be too small. Webb six point weights, 9,999 draws, null imposed.
3. SARIMA instead of exponential smoothing for the expected path.
4. Visitors: foreign vs non resident Jamaican stopovers against an expected path
   (same month in 2024 scaled by each segment's Jan to Sep 2025 growth).
"""
import json
import warnings

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

from model import RAW, ROOT, WEST, load_corridors, load_parishes, sarima

OUT = ROOT / "outputs"
EVENT = ["2025-09", "2025-10", "2025-11", "2025-12", "2026-01", "2026-02", "2026-03"]
res = {}

# ---------------------------------------------------------------- parish panel
p = load_parishes().drop(columns="total_remittances")
long = p.stack().rename("usd").reset_index()
long.columns = ["month", "parish", "usd"]
long = long[long.month >= pd.Period("2022-01", "M")].copy()
long["log_usd"] = np.log(long.usd)
long["mstr"] = long.month.astype(str)
long["west"] = long.parish.isin(WEST).astype(int)

dmg = pd.read_csv(RAW / "grade_melissa_damage_by_parish.csv").set_index("parish")
# Kingston and St. Andrew are one series here, so combine their damage over their
# combined exposed value (exposed value = damage / share).
tev = dmg.total_damage_usd_m / (dmg.damage_pct_of_exposed_value / 100)
ksa = (dmg.loc[["kingston", "st_andrew"], "total_damage_usd_m"].sum()
       / tev[["kingston", "st_andrew"]].sum() * 100)
share = dmg.damage_pct_of_exposed_value.drop(["kingston", "st_andrew"]).to_dict()
share["kingston_st_andrew"] = ksa
long["damage"] = long.parish.map(share)
assert long.damage.notna().all()


def event_terms(df, var):
    names = []
    for m in EVENT:
        k = f"{var}_{m.replace('-', '_')}"
        df[k] = (df.mstr == m) * df[var]
        names.append(k)
    return names


with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    # 1. damage intensity, per 10 points of damage share
    long["damage10"] = long.damage / 10
    terms = event_terms(long, "damage10")
    fit = smf.ols("log_usd ~ C(parish) + C(mstr) + " + " + ".join(terms), data=long).fit(
        cov_type="cluster", cov_kwds={"groups": long.parish})
res["damage_intensity_per_10pts"] = {
    m: {"pct": round(float((np.exp(fit.params[t]) - 1) * 100), 1), "p": round(float(fit.pvalues[t]), 3)}
    for m, t in zip(EVENT, terms)}

# 2. wild cluster bootstrap for the November west coefficient (null imposed)
long["w_nov"] = ((long.mstr == "2025-11") & (long.west == 1)).astype(float)
other = [m for m in EVENT if m != "2025-11"]
for m in other:
    long[f"w_{m.replace('-', '_')}"] = ((long.mstr == m) & (long.west == 1)).astype(float)
ctrl = "C(parish) + C(mstr) + " + " + ".join(f"w_{m.replace('-', '_')}" for m in other)
with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    full = smf.ols(f"log_usd ~ {ctrl} + w_nov", data=long).fit(
        cov_type="cluster", cov_kwds={"groups": long.parish})
    restricted = smf.ols(f"log_usd ~ {ctrl}", data=long).fit()
t_obs = full.tvalues["w_nov"]
X = full.model.exog
names = full.model.exog_names
j = names.index("w_nov")
XtX_inv = np.linalg.pinv(X.T @ X)
groups = long.parish.values
gidx = {g: np.where(groups == g)[0] for g in np.unique(groups)}
fitted0, resid0 = restricted.fittedvalues.values, restricted.resid.values
webb = np.array([-np.sqrt(1.5), -1, -np.sqrt(0.5), np.sqrt(0.5), 1, np.sqrt(1.5)])
rng = np.random.default_rng(7)
B, G = 9999, len(gidx)


def cluster_t(y):
    beta = XtX_inv @ X.T @ y
    e = y - X @ beta
    meat = np.zeros((X.shape[1], X.shape[1]))
    for idx in gidx.values():
        s = X[idx].T @ e[idx]
        meat += np.outer(s, s)
    n, k = X.shape
    c = G / (G - 1) * (n - 1) / (n - k)
    V = c * XtX_inv @ meat @ XtX_inv
    return beta[j] / np.sqrt(V[j, j])


t_star = np.empty(B)
keys = list(gidx)
for b in range(B):
    w = rng.choice(webb, size=G)
    e_star = resid0.copy()
    for g, wg in zip(keys, w):
        e_star[gidx[g]] *= wg
    t_star[b] = cluster_t(fitted0 + e_star)
res["wild_bootstrap_nov_west"] = {
    "estimate_pct": round(float((np.exp(full.params["w_nov"]) - 1) * 100), 1),
    "t": round(float(t_obs), 2),
    "p_cluster": round(float(full.pvalues["w_nov"]), 4),
    "p_wild_bootstrap": round(float(np.mean(np.abs(t_star) >= abs(t_obs))), 4),
    "draws": B, "clusters": G}

# 3. SARIMA expected path for Melissa
d = load_corridors()
sar = {}
for col in ["total_remittances", "united_states", "united_kingdom", "canada", "cayman_islands"]:
    lf = pd.Period("2025-10", "M")
    fc = sarima(d[col].loc[:lf - 1], 2)
    act = d[col].loc[lf:lf + 1].values
    gap = (act / fc - 1) * 100
    sar[col] = {"oct_pct": round(float(gap[0]), 1), "nov_pct": round(float(gap[1]), 1),
                "oct_nov_combined_pct": round(float((act.sum() / fc.sum() - 1) * 100), 1)}
res["sarima_melissa"] = sar

# 4. Visitors by segment
v = pd.read_csv(RAW / "jtb_stopovers_by_segment.csv", parse_dates=["date"])
v = v.groupby(["date", "segment"]).stopovers.sum().unstack()
v.index = v.index.to_period("M")
vis = {}
for seg in v.columns:
    s = v[seg]
    growth = s.loc["2025-01":"2025-09"].sum() / s.loc["2024-01":"2024-09"].sum()
    rows = {}
    for m in ["2025-10", "2025-11", "2025-12"]:
        pm = pd.Period(m, "M")
        exp = s.loc[pm - 12] * growth
        rows[m] = {"actual": int(s.loc[pm]), "expected": int(round(exp)),
                   "gap_pct": round(float((s.loc[pm] / exp - 1) * 100), 1),
                   "yoy_pct": round(float((s.loc[pm] / s.loc[pm - 12] - 1) * 100), 1)}
    vis[seg] = {"pre_storm_growth_jan_sep_2025_pct": round(float((growth - 1) * 100), 1), "months": rows}
    q4_act = s.loc["2025-10":"2025-12"].sum()
    q4_exp = sum(r["expected"] for r in rows.values())
    vis[seg]["oct_dec_gap_pct"] = round(float((q4_act / q4_exp - 1) * 100), 1)
res["visitors"] = vis

(OUT / "robustness_summary.json").write_text(json.dumps(res, indent=1))
print(json.dumps(res, indent=1))
