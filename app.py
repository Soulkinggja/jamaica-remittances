"""Jamaica Remittances Tracker and Forecast

Monthly remittance inflows to Jamaica from Bank of Jamaica statistics, by source
country and by parish, with a forecast to December 2027 and an analysis of how
remittances responded to Hurricanes Beryl and Melissa.

Run locally:  streamlit run app.py
"""
import json
import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT / "src"))
from model import WEST, load_corridors, load_parishes  # noqa: E402

OUT = ROOT / "outputs"

BLUE = "#2a78d6"
ORANGE = "#e07b39"
GREEN = "#2a9d6b"
RED = "#e34948"
GREY = "#898781"
INK = "#0b0b0b"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"
SURFACE = "#fcfcfb"

NAMES = {
    "total_remittances": "All sources",
    "united_states": "United States",
    "united_kingdom": "United Kingdom",
    "canada": "Canada",
    "cayman_islands": "Cayman Islands",
    "other_countries": "Other countries",
    "other_remittances": "Other channels (not remittance companies)",
}
COLORS = {"united_states": BLUE, "united_kingdom": ORANGE, "canada": GREEN,
          "cayman_islands": RED, "other_countries": GREY}
STORMS = {"2024-07": "Beryl", "2025-10": "Melissa"}

st.set_page_config(page_title="Jamaica Remittances Tracker", page_icon="💸", layout="wide")


@st.cache_data
def load():
    c = load_corridors()
    c.index = c.index.to_timestamp()
    p = load_parishes()
    p.index = p.index.to_timestamp()
    fc = pd.read_csv(OUT / "forecast.csv", parse_dates=["month"])
    gaps = pd.read_csv(OUT / "storm_gaps.csv")
    scores = pd.read_csv(OUT / "backtest_scores.csv")
    fsum = json.loads((OUT / "forecast_summary.json").read_text())
    ssum = json.loads((OUT / "storm_summary.json").read_text())
    return c, p, fc, gaps, scores, fsum, ssum


c, p, fc, gaps, scores, fsum, ssum = load()


def style(fig, height=420, ytitle="USD millions"):
    fig.update_layout(height=height, plot_bgcolor=SURFACE, paper_bgcolor=SURFACE,
                      font=dict(color=INK), margin=dict(t=30, b=10, l=10, r=10),
                      legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
                      yaxis=dict(title=ytitle, gridcolor=GRID, zerolinecolor=AXIS),
                      xaxis=dict(gridcolor=GRID), hovermode="x unified")
    return fig


def mark_storms(fig):
    for m, name in STORMS.items():
        x = pd.Timestamp(m)
        fig.add_vline(x=x, line_width=1, line_dash="dot", line_color=RED)
        fig.add_annotation(x=x, y=1.0, yref="paper", text=name, showarrow=False,
                           font=dict(size=10, color=RED), xanchor="left")


# ------------------------------------------------------------------ header
st.title("💸 Jamaica Remittances Tracker and Forecast")
st.caption("Money sent home to Jamaica each month, by source country and by parish, from Bank of "
           "Jamaica statistics. January 2012 to " + c.index[-1].strftime("%B %Y") + ".")

last = c.index[-1]
tot = c["total_remittances"]
yoy = (tot.iloc[-1] / tot.loc[last - pd.DateOffset(years=1)] - 1) * 100
us_share = c["united_states"].loc["2025"].sum() / tot.loc["2025"].sum() * 100
k1, k2, k3, k4 = st.columns(4)
k1.metric("Received in 2025", f"US${fsum['actual_2025'] / 1000:.2f}bn",
          f"{(fsum['actual_2025'] / fsum['actual_2024'] - 1) * 100:+.1f}% vs 2024")
k2.metric(f"Received in {last:%B %Y}", f"US${tot.iloc[-1]:.0f}m", f"{yoy:+.1f}% vs a year earlier")
k3.metric("Forecast for 2026", f"US${fsum['forecast_2026_total'] / 1000:.2f}bn",
          f"80% range US${fsum['range80_2026'][0] / 1000:.2f}bn to {fsum['range80_2026'][1] / 1000:.2f}bn",
          delta_color="off")
k4.metric("Share from the United States, 2025", f"{us_share:.0f}%")

st.divider()

# ------------------------------------------------------------------ total + forecast
st.subheader("Monthly remittances and the forecast to December 2027")
f = fc[fc.series == "total_remittances"]
fig = go.Figure()
fig.add_trace(go.Scatter(x=list(f.month) + list(f.month[::-1]), y=list(f.high80) + list(f.low80[::-1]),
                         fill="toself", fillcolor="rgba(42,120,214,0.15)", line=dict(width=0),
                         name="80% range", hoverinfo="skip"))
fig.add_trace(go.Scatter(x=tot.index, y=tot, name="Actual", line=dict(color=BLUE, width=2),
                         hovertemplate="%{x|%b %Y}: US$%{y:.1f}m<extra></extra>"))
fig.add_trace(go.Scatter(x=f.month, y=f.forecast, name="Forecast", mode="lines", line=dict(color=BLUE, width=2, dash="dash"),
                         hovertemplate="%{x|%b %Y}: US$%{y:.1f}m<extra>forecast</extra>"))
mark_storms(fig)
st.plotly_chart(style(fig, 440), width="stretch")
st.caption(f"Forecast: {fsum['model']}, chosen because it had the lowest error in the backtest below. "
           f"2027 total: US${fsum['forecast_2027_total'] / 1000:.2f}bn, 80% range "
           f"US${fsum['range80_2027'][0] / 1000:.2f}bn to {fsum['range80_2027'][1] / 1000:.2f}bn. "
           "The big step up in 2020 and 2021 is the COVID period, when more money moved through "
           "formal channels and families abroad sent more.")

# ------------------------------------------------------------------ by source
st.subheader("Where the money comes from")
left, right = st.columns([3, 2])
with left:
    view = st.radio("Show", ["Monthly", "Yearly totals"], horizontal=True)
    fig = go.Figure()
    for col in ["united_states", "united_kingdom", "canada", "cayman_islands", "other_countries"]:
        s = c[col] if view == "Monthly" else c[col].groupby(c.index.year).sum()
        x = s.index if view == "Monthly" else s.index.astype(str)
        fig.add_trace(go.Scatter(x=x, y=s, name=NAMES[col], line=dict(color=COLORS[col], width=2),
                                 hovertemplate="%{y:.1f}<extra>" + NAMES[col] + "</extra>"))
    if view == "Monthly":
        mark_storms(fig)
    st.plotly_chart(style(fig, 400), width="stretch")
with right:
    yr = st.selectbox("Year", sorted(c.index.year.unique(), reverse=True)[1:], index=0)
    sub = c.loc[str(yr)]
    tab = pd.DataFrame({
        "Source": [NAMES[x] for x in ["united_states", "united_kingdom", "canada", "cayman_islands",
                                      "other_countries", "other_remittances"]],
        "US$ millions": [sub[x].sum() for x in ["united_states", "united_kingdom", "canada",
                                                "cayman_islands", "other_countries", "other_remittances"]],
    })
    tab["Share"] = tab["US$ millions"] / sub["total_remittances"].sum() * 100
    st.dataframe(tab.style.format({"US$ millions": "{:,.1f}", "Share": "{:.1f}%"}),
                 hide_index=True, width="stretch")
    st.caption("Country figures cover remittance companies. 'Other channels' is money that came through "
               "banks and other routes, which BOJ does not split by country.")

st.divider()

# ------------------------------------------------------------------ hurricanes
st.subheader("What Hurricane Melissa did to remittances")
st.markdown(
    "Melissa made landfall on 28 October 2025. For each source country, the chart compares what "
    "arrived with what a model trained only on data before the storm expected. In a normal month "
    f"the model is off by about {ssum['placebo_one_month']['mean_abs_gap_pct']:.1f}%, and 95% of normal "
    f"months are within {ssum['placebo_one_month']['p95_abs_gap_pct']:.1f}%."
)
mel = gaps[(gaps.storm == "Melissa") & (gaps.series != "total_remittances")]
fig = go.Figure()
for col in ["united_states", "united_kingdom", "canada", "cayman_islands"]:
    s = mel[mel.series == col]
    fig.add_trace(go.Bar(x=pd.to_datetime(s.month).dt.strftime("%b %Y"), y=s.gap_pct, name=NAMES[col],
                         marker_color=COLORS[col], hovertemplate="%{y:+.1f}%<extra>" + NAMES[col] + "</extra>"))
band = ssum["placebo_one_month"]["p95_abs_gap_pct"]
fig.add_hrect(y0=-band, y1=band, fillcolor=GREY, opacity=0.12, line_width=0)
fig.add_hline(y=0, line_color=AXIS)
fig = style(fig, 400, "% above or below expected")
fig.update_layout(barmode="group")
st.plotly_chart(fig, width="stretch")
st.caption("Grey band: the range that covers 95% of normal months.")

a, b = st.columns(2)
with a:
    st.markdown("**By parish, November 2025 vs November 2024**")
    g = pd.Series(ssum["parish_yoy_nov_2025"]).sort_values()
    labels = [x.replace("_", " ").title().replace("St ", "St. ") for x in g.index]
    fig = go.Figure(go.Bar(x=g.values, y=labels, orientation="h",
                           marker_color=[RED if k in WEST else BLUE for k in g.index],
                           hovertemplate="%{x:+.1f}%<extra></extra>"))
    fig.add_vline(x=0, line_color=AXIS)
    fig = style(fig, 430, "")
    fig.update_layout(xaxis_title="% change", hovermode=False)
    st.plotly_chart(fig, width="stretch")
    st.caption("Red: the five western parishes hit hardest (Hanover, Westmoreland, St. James, "
               "St. Elizabeth, Trelawny). Kingston and St. Andrew are combined because BOJ reports "
               "them together from 2024.")
with b:
    did = ssum["parish_did_west_vs_rest"]
    tr = ssum["transfers"]
    st.markdown("**What the numbers say**")
    st.markdown(
        f"- **October:** money from every main source country came in 10% to 14% below the "
        f"expected level, well outside the normal range.\n"
        f"- **November:** money from the US, UK and Canada bounced back 11% to 19% above expected, "
        f"and the number of transfers was "
        f"{tr['2025-11']['count_yoy_pct']:+.1f}% on a year earlier. The average transfer barely changed "
        f"(US${tr['2025-11']['avg_size_usd']:.0f}), so more people sent money, not bigger amounts.\n"
        f"- **October and November together:** for the US, UK and Canada, within 4% of what was "
        f"expected. The storm moved the timing more than the total.\n"
        f"- **Where it landed:** in November the western parishes received "
        f"{abs(did['2025-11']['west_vs_rest_pct']):.0f}% less than the rest of the island, after allowing "
        f"for each parish's normal level and the month. By December the gap was gone.\n"
        f"- **Beryl (July 2024)** left no lasting mark: over the six months after landfall, the total "
        f"was within 0.3% of expected."
    )

st.divider()

# ------------------------------------------------------------------ backtest
st.subheader("How accurate is the forecast?")
show = scores.rename(columns={"model": "Model", "mape_1m": "Next month error (%)",
                              "mape_12m_total": "Next 12 months total error (%)",
                              "mape_1m_no_storms": "Next month error, storm months removed (%)"})
st.dataframe(show[["Model", "Next month error (%)", "Next 12 months total error (%)",
                   "Next month error, storm months removed (%)"]],
             hide_index=True, width="stretch")
st.caption("Rolling backtest: every month from January 2023 onward, each model is trained only on the "
           "data available then and scored on what came next. Error is the average absolute "
           "percentage miss. The seasonal naive models are the bar to beat.")

with st.expander("Data sources and notes"):
    st.markdown(
        "- Bank of Jamaica statistics tables ES.RMT.00 to ES.RMT.03 (inflows by corridor, outflows, "
        "parish, number of transfers), downloaded November 2026.\n"
        "- Values are US dollar equivalents in millions. Totals here are gross inflows; BOJ's "
        "headline 'net remittances' also subtracts money sent out of Jamaica.\n"
        "- Parish data cover remittance companies only and start in July 2020.\n"
        "- February 2026 parish figures use BOJ's revised release (November 2026). "
        "The parish table records where money is paid out."
    )
    st.download_button("Download the source country data (CSV)", c.to_csv().encode(),
                       "jamaica_remittances_by_source.csv", "text/csv")

st.caption("Built by Devin McIntosh. Code and data: github.com/Soulkinggja/jamaica-remittances")
