"""Figures for the paper draft."""
import json
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from model import ROOT, RAW, WEST, load_corridors, load_parishes

OUT = ROOT / "outputs"
FIG = ROOT / "paper" / "figures"
plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.grid": True, "grid.color": "#e6e6e6", "figure.dpi": 150})
BLUE, ORANGE, GREEN, RED, GREY = "#2a78d6", "#e07b39", "#2a9d6b", "#e34948", "#898781"

c = load_corridors(); c.index = c.index.to_timestamp()
fig, ax = plt.subplots(figsize=(8, 3.6))
ax.plot(c.index, c.total_remittances, color=BLUE, lw=1.6)
for d, n in [("2024-07", "Beryl"), ("2025-10", "Melissa"), ("2020-03", "COVID 19")]:
    ax.axvline(pd.Timestamp(d), color=RED if n != "COVID 19" else GREY, ls=":", lw=1)
    ax.text(pd.Timestamp(d), ax.get_ylim()[1] * 0.98, " " + n, color=RED if n != "COVID 19" else GREY, fontsize=8, va="top")
ax.set_ylabel("US$ millions per month")
ax.set_title("Figure 1. Remittance inflows to Jamaica, January 2012 to August 2026", loc="left", fontsize=10)
fig.text(0.01, 0.01, "Source: Bank of Jamaica, table ES.RMT.01.", fontsize=7, color=GREY)
fig.tight_layout(rect=(0, 0.03, 1, 1)); fig.savefig(FIG / "fig1_remittances.png")

g = pd.read_csv(OUT / "storm_gaps.csv"); s = json.loads((OUT / "storm_summary.json").read_text())
m = g[(g.storm == "Melissa") & (g.series != "total_remittances")]
months = sorted(m.month.unique()); names = {"united_states": "United States", "united_kingdom": "United Kingdom", "canada": "Canada", "cayman_islands": "Cayman Islands"}
cols = {"united_states": BLUE, "united_kingdom": ORANGE, "canada": GREEN, "cayman_islands": RED}
fig, ax = plt.subplots(figsize=(8, 3.8)); w = 0.2
band = s["placebo_one_month"]["p95_abs_gap_pct"]
ax.axhspan(-band, band, color=GREY, alpha=0.15, lw=0, label="95% of normal months")
for i, k in enumerate(names):
    v = m[m.series == k].set_index("month").gap_pct.reindex(months)
    ax.bar([j + (i - 1.5) * w for j in range(len(months))], v.values, w, color=cols[k], label=names[k])
ax.axhline(0, color="#999", lw=0.8)
ax.set_xticks(range(len(months))); ax.set_xticklabels([pd.Period(x).strftime("%b %Y") for x in months])
ax.set_ylabel("% above or below expected"); ax.set_ylim(-16, 27); ax.legend(ncol=5, fontsize=7, loc="upper center", frameon=False)
ax.set_title("Figure 2. Remittances against a pre storm forecast, by source country", loc="left", fontsize=10)
fig.text(0.01, 0.01, "Exponential smoothing fitted to January 2012 to September 2025. Source: Bank of Jamaica; author's calculations.", fontsize=7, color=GREY)
fig.tight_layout(rect=(0, 0.03, 1, 1)); fig.savefig(FIG / "fig2_melissa_gaps.png")

p = load_parishes()
yoy = (p.loc[pd.Period("2025-11", "M")] / p.loc[pd.Period("2024-11", "M")] - 1) * 100
dmg = pd.read_csv(RAW / "grade_melissa_damage_by_parish.csv").set_index("parish")
tev = dmg.total_damage_usd_m / (dmg.damage_pct_of_exposed_value / 100)
share = dmg.damage_pct_of_exposed_value.drop(["kingston", "st_andrew"])
share["kingston_st_andrew"] = dmg.loc[["kingston", "st_andrew"], "total_damage_usd_m"].sum() / tev[["kingston", "st_andrew"]].sum() * 100
fig, ax = plt.subplots(figsize=(7, 4.2))
for k, x in share.items():
    y = yoy[k]; col = RED if k in WEST else BLUE
    ax.scatter(x, y, color=col, s=36, zorder=3)
    lab = k.replace("_", " ").title().replace("St ", "St. ").replace("Kingston St. Andrew", "Kingston and St. Andrew")
    ax.annotate(lab, (x, y), xytext=(4, -10 if k == "clarendon" else 3), textcoords="offset points", fontsize=7)
ax.axhline(0, color="#999", lw=0.8)
ax.set_xlabel("Melissa damage, % of exposed value (World Bank GRADE)"); ax.set_ylabel("Remittances, Nov 2025 vs Nov 2024 (%)")
ax.set_title("Figure 3. November remittance growth by parish against storm damage", loc="left", fontsize=10)
fig.text(0.01, 0.01, "Remittance companies only. Sources: Bank of Jamaica, table ES.RMT.03; World Bank (2025).", fontsize=7, color=GREY)
fig.tight_layout(rect=(0, 0.03, 1, 1)); fig.savefig(FIG / "fig3_parish_damage.png")

r = json.loads((OUT / "robustness_summary.json").read_text())["visitors"]
fig, ax = plt.subplots(figsize=(7, 3.6)); mths = ["2025-10", "2025-11", "2025-12"]; w = 0.35
for i, (seg, col) in enumerate([("Foreign nationals", ORANGE), ("Non resident Jamaicans", BLUE)]):
    vals = [r[seg]["months"][mm]["gap_pct"] for mm in mths]
    bars = ax.bar([j + (i - 0.5) * w for j in range(3)], vals, w, color=col, label=seg)
    for b, v in zip(bars, vals):
        ax.text(b.get_x() + b.get_width() / 2, v - 3, f"{v:.0f}%", ha="center", va="top", fontsize=7)
ax.axhline(0, color="#999", lw=0.8); ax.set_ylim(-82, 5)
ax.set_xticks(range(3)); ax.set_xticklabels(["Oct 2025", "Nov 2025", "Dec 2025"])
ax.set_ylabel("% below expected"); ax.legend(frameon=False, fontsize=8, loc="lower right")
ax.set_title("Figure 4. Stopover arrivals against each group's pre storm trend", loc="left", fontsize=10)
fig.text(0.01, 0.01, "Expected = same month of 2024 x Jan to Sep 2025 growth. Source: Jamaica Tourist Board; author's calculations.", fontsize=7, color=GREY)
fig.tight_layout(rect=(0, 0.03, 1, 1)); fig.savefig(FIG / "fig4_visitors.png")
print("ok")
