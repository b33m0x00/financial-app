"""Company financial analysis - Streamlit UI.

Run:  streamlit run app.py
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import fin
import report
from excel_export import build_workbook

st.set_page_config(page_title="Company Financial Analysis", layout="wide")

# Validated categorical palette, fixed order (dataviz reference palette)
C = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
BAND = "rgba(27,175,122,0.12)"
FONT = dict(family="system-ui, -apple-system, Segoe UI, sans-serif", size=13)


def style(fig, height=380, title=None, legend_space=10):
    """Common look: title top-left, legend BELOW the plot so it never covers bars or titles."""
    fig.update_layout(height=height, font=FONT, hovermode="x unified", bargap=0.3, bargroupgap=0.08,
                      title=dict(text=title, x=0, xanchor="left", y=0.98, yanchor="top", font_size=15) if title else None,
                      margin=dict(l=10, r=10, t=48 if title else 16, b=legend_space, autoexpand=True),
                      legend=dict(orientation="h", x=0, xanchor="left", y=-0.12, yanchor="top",
                                  bgcolor="rgba(0,0,0,0)", font_size=12, title_text=""))
    fig.update_xaxes(type="category", showgrid=False, automargin=True)
    fig.update_yaxes(gridcolor="rgba(128,128,128,0.18)", zeroline=True, zerolinecolor="rgba(128,128,128,0.4)",
                     automargin=True)
    return fig


def pad_range(values, extra=(0.0,)):
    """Y range with headroom so value labels above points are not clipped."""
    v = np.array([x for x in list(values) + list(extra) if x is not None and np.isfinite(x)], dtype=float)
    if not len(v):
        return None
    lo, hi = v.min(), v.max()
    span = (hi - lo) or abs(hi) or 1
    return [lo - span * 0.12, hi + span * 0.22]


st.markdown("""<style>
.block-container {padding-top: 2.2rem;}
[data-testid="stMetric"] {background: rgba(128,128,128,0.06); border-radius: 10px; padding: 10px 14px;}
[data-testid="stMetricLabel"] p {font-size: 0.85rem;}
h3 {margin-top: 0.6rem;}
</style>""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Sidebar: data source
# ---------------------------------------------------------------------------
st.sidebar.title("Data source")
mode = st.sidebar.radio("Get statements from", ["Yahoo Finance (listed companies)", "Manual entry (any company)"])

data, info = None, {}
if mode.startswith("Yahoo"):
    q = st.sidebar.text_input("Company name or ticker", value="Apple")

    @st.cache_data(ttl=3600, show_spinner=False)
    def _search(q):
        return fin.search_company(q)

    @st.cache_data(ttl=3600, show_spinner="Downloading statements from Yahoo Finance...")
    def _load(sym):
        return fin.from_yahoo(sym)

    if q.strip():
        try:
            hits = _search(q.strip())
        except Exception as e:
            hits = []
            st.sidebar.error(f"Search failed: {e}")
        if hits:
            choice = st.sidebar.selectbox("Pick the company", hits,
                                          format_func=lambda h: f"{h['name']} ({h['symbol']}, {h['exchange']})")
            try:
                data, info = _load(choice["symbol"])
                info["symbol"] = choice["symbol"]
            except Exception as e:
                st.error(f"Could not load {choice['symbol']}: {e}")
        else:
            st.sidebar.warning("No match. Try ticker (e.g. MSFT, TLV.RO for Romanian companies).")
else:
    st.sidebar.caption("Type values from the company's balance sheet & income statement "
                       "(e.g. Moldovan/Romanian companies not on Yahoo). Blank derived lines are auto-filled.")
    years = st.sidebar.multiselect("Years", list(range(2015, 2027)), default=[2019, 2020, 2021, 2022, 2023, 2024])
    name = st.sidebar.text_input("Company name", "Company X")
    cur = st.sidebar.text_input("Currency", "MDL (thousand lei)")
    blank = pd.DataFrame(np.nan, index=[fin.INPUTS[k][0] for k in fin.MANUAL_KEYS], columns=[str(y) for y in sorted(years)])
    up = st.sidebar.file_uploader("...or upload a filled Data sheet (.xlsx exported by this app)", type=["xlsx"])
    if up is not None:
        raw = pd.read_excel(up, sheet_name="Data", header=1, index_col=0)
        raw = raw.drop(columns=[c for c in raw.columns if str(c).startswith("Statement")], errors="ignore")
        raw.columns = [str(int(c)) for c in raw.columns]
        blank = raw.reindex(blank.index)
    st.subheader("Manual input (currency units as you choose)")
    edited = st.data_editor(blank, width="stretch", height=36 * (len(blank) + 1))
    label_to_key = {fin.INPUTS[k][0]: k for k in fin.MANUAL_KEYS}
    df = edited.rename(index=label_to_key).apply(pd.to_numeric, errors="coerce")
    df.columns = [int(c) for c in df.columns]
    if df.notna().any().any():
        data = df
        info = {"name": name, "currency": cur}

if data is None:
    st.title("Company Financial Analysis")
    st.info("Pick a company in the sidebar (or enter data manually) to start.")
    st.stop()

d = fin.fill_derived(data)
ratios = fin.compute_ratios(d)
scores, parts = fin.compute_scores(d, info.get("market_cap") if mode.startswith("Yahoo") else None)
years = list(d.columns)

# Display scale
big = np.nanmax(np.abs(d.values)) if np.isfinite(d.values).any() else 0
scale, unit = (1e9, "bn") if big >= 1e11 else (1e6, "mn") if big >= 1e6 else (1, "")
cur = info.get("currency", "")
unit_label = f"{cur} {unit}".strip()

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
st.title(info.get("name", "Company"))
meta = " · ".join(x for x in [info.get("symbol"), info.get("sector"), info.get("industry"), info.get("country"),
                              f"figures in {unit_label}" if unit_label else None] if x)
st.caption(meta)
if d.loc["current_assets"].isna().all():
    st.warning("This company does not split assets/liabilities into current vs long-term (typical for banks and "
               "insurers), so liquidity ratios and bankruptcy models cannot be computed. Pick an industrial/trading company.")

last, prev = years[-1], years[-2] if len(years) > 1 else None


def kpi(col, label, key, src, fmt="{:,.1f}", suffix=""):
    v = src.at[key, last] / (scale if src is d else 1)
    delta = None
    if prev is not None and pd.notna(src.at[key, prev]) and pd.notna(v):
        pv = src.at[key, prev] / (scale if src is d else 1)
        delta = fmt.format(v - pv) + suffix
    col.metric(f"{label} {last}", "n/a" if pd.isna(v) else fmt.format(v) + suffix, delta)


k = st.columns(6)
kpi(k[0], "Revenue", "revenue", d)
kpi(k[1], "Net profit", "net_profit", d)
kpi(k[2], "Total assets", "total_assets", d)
kpi(k[3], "Return on sales", "return_on_sales", ratios, suffix="%")
kpi(k[4], "Current ratio", "current_liquidity", ratios, fmt="{:.2f}")
kpi(k[5], "Debt ratio", "debt_ratio", ratios, fmt="{:.2f}")

tabs = st.tabs(["Statements", "Profit & costs", "Balance structure", "Ratios", "Bankruptcy risk",
                "Formulas explained", "Export"])

# ---------------------------------------------------------------------------
# 1. Statements
# ---------------------------------------------------------------------------
with tabs[0]:
    if info.get("summary"):
        with st.expander("What the company does"):
            st.write(info["summary"])
    for stmt in ["Balance sheet", "Income statement", "Cash flow"]:
        keys = [k for k, v in fin.INPUTS.items() if v[1] == stmt]
        t = (d.loc[keys] / scale).copy()
        t.index = [fin.INPUTS[k][0] for k in keys]
        st.subheader(f"{stmt} ({unit_label})")
        st.dataframe(t.style.format("{:,.1f}", na_rep="–"), width="stretch")
    st.subheader("Horizontal analysis – change vs previous year, %")
    h = fin.horizontal_analysis(d).iloc[:, 1:]
    h.index = [fin.INPUTS[k][0] for k in h.index]
    st.dataframe(h.style.format("{:+.1f}%", na_rep="–").background_gradient(cmap="RdYlGn", vmin=-50, vmax=50, axis=None),
                 width="stretch")

# ---------------------------------------------------------------------------
# 2. Profit & costs
# ---------------------------------------------------------------------------
with tabs[1]:
    c1, c2 = st.columns(2)
    fig = go.Figure()
    for i, (key, lab) in enumerate([("revenue", "Revenue"), ("gross_profit", "Gross profit"),
                                    ("operating_profit", "Operating profit"), ("net_profit", "Net profit")]):
        fig.add_bar(x=years, y=d.loc[key] / scale, name=lab, marker_color=C[i],
                    hovertemplate="%{y:,.1f}")
    c1.plotly_chart(style(fig, height=420, title=f"From revenue to net profit ({unit_label})", legend_space=90), width="stretch")

    fig = go.Figure()
    cost_keys = [("cost_of_sales", "Cost of sales"), ("sga", "Distribution + G&A"), ("rd", "R&D"),
                 ("other_opex", "Other operational")]
    for i, (key, lab) in enumerate(cost_keys):
        fig.add_bar(x=years, y=d.loc[key].fillna(0) / scale, name=lab, marker_color=C[i],
                    marker_line_width=2, marker_line_color="rgba(255,255,255,0.9)", hovertemplate="%{y:,.1f}")
    fig.update_layout(barmode="stack")
    c2.plotly_chart(style(fig, height=420, title=f"Costs analysis – structure of expenses ({unit_label})",
                          legend_space=90),
                    width="stretch")

    costs = d.loc[[k for k, _ in cost_keys]].fillna(0)
    ct = (costs / scale).copy()
    ct.loc["total"] = ct.sum()
    ct.loc["Net profit (loss) from operating activities"] = d.loc["revenue"] / scale - ct.loc["total"]
    share = costs.div(costs.sum()) * 100
    ct.index = [dict(cost_keys).get(i, i) for i in ct.index]
    share.index = [dict(cost_keys)[i] for i in share.index]
    st.markdown("**Costs analysis table** (same as sheet *Costs analysis* in your Excel)")
    st.dataframe(ct.style.format("{:,.1f}"), width="stretch")
    st.markdown("**Share of each cost in total costs, %**")
    st.dataframe(share.style.format("{:.1f}%"), width="stretch")

    fig = go.Figure()
    for i, key in enumerate(["gross_margin", "return_on_sales", "net_margin"]):
        fig.add_scatter(x=years, y=ratios.loc[key], name=fin.RATIOS[key][0], mode="lines+markers",
                        line=dict(color=C[i], width=2), marker=dict(size=9), hovertemplate="%{y:.1f}%")
    st.plotly_chart(style(fig, title="Margins, % of revenue"), width="stretch")

# ---------------------------------------------------------------------------
# 3. Balance structure
# ---------------------------------------------------------------------------
with tabs[2]:
    noncur = d.loc["total_assets"] - d.loc["current_assets"]
    other_ca = d.loc["current_assets"] - d.loc[["cash", "st_investments", "receivables", "inventory"]].fillna(0).sum()
    assets = [("Cash", d.loc["cash"]), ("ST investments", d.loc["st_investments"]),
              ("Receivables", d.loc["receivables"]), ("Inventories", d.loc["inventory"]),
              ("Other current", other_ca), ("Long-term (fixed) assets", noncur)]
    top = float(np.nanmax(d.loc["total_assets"].values) / scale) * 1.05
    figs = []
    fig = go.Figure()
    for i, (lab, s) in enumerate(assets):
        fig.add_bar(x=years, y=s.fillna(0) / scale, name=lab, marker_color=C[i],
                    marker_line_width=2, marker_line_color="rgba(255,255,255,0.9)", hovertemplate="%{y:,.1f}")
    figs.append((fig, f"Assets – what the company owns ({unit_label})"))
    fig = go.Figure()
    fin_src = [("ST debt", d.loc["current_liabilities"], C[7]), ("LT debt", d.loc["noncurrent_liabilities"], C[3]),
               ("Equity", d.loc["equity"], C[6])]
    for lab, s, col in fin_src:
        fig.add_bar(x=years, y=s / scale, name=lab, marker_color=col,
                    marker_line_width=2, marker_line_color="rgba(255,255,255,0.9)", hovertemplate="%{y:,.1f}")
    figs.append((fig, f"Liabilities + equity – how it is financed ({unit_label})"))
    low = min(0.0, float(np.nanmin(d.loc["equity"].values) / scale) * 1.1)
    for col, (fig, title) in zip(st.columns(2), figs):
        fig.update_layout(barmode="relative")
        fig.update_yaxes(range=[low, top])
        col.plotly_chart(style(fig, height=520, title=title, legend_space=120), width="stretch")
    st.caption("Basic rule: Assets = Liabilities + Equity. Negative equity (bars below zero) means accumulated "
               "losses/buybacks exceed paid-in capital.")
    st.subheader("Vertical analysis – % of total assets")
    v = fin.vertical_analysis(d)
    v.index = [fin.INPUTS[k][0] for k in v.index]
    st.dataframe(v.style.format("{:.1f}%", na_rep="–"), width="stretch")

# ---------------------------------------------------------------------------
# 4. Ratios
# ---------------------------------------------------------------------------
NORM_BANDS = {"abs_liquidity": (0.2, 0.25), "quick_liquidity": (0.7, 0.8), "current_liquidity": (2, 2.5),
              "general_solvency": (2, None), "debt_ratio": (None, 0.5), "debt_to_equity": (None, 1),
              "interest_coverage": (3, None)}


def ratio_chart(key, color):
    label, _, formula, norm, _, unit = fin.RATIOS[key]
    y = ratios.loc[key]
    fig = go.Figure()
    if key in NORM_BANDS:
        lo, hi = NORM_BANDS[key]
        rng = pad_range(y.values, [b for b in (lo, hi) if b is not None])
        fig.add_hrect(y0=lo if lo is not None else rng[0], y1=hi if hi is not None else rng[1],
                      fillcolor=BAND, line_width=0, annotation_text=f"norm {norm}",
                      annotation_position="top left", annotation_font_size=11)
    fig.add_scatter(x=years, y=y, mode="lines+markers+text", line=dict(color=color, width=2),
                    marker=dict(size=9), text=[f"{v:.2f}" if pd.notna(v) else "" for v in y],
                    textposition="top center", showlegend=False, cliponaxis=False,
                    hovertemplate=f"{label}: %{{y:.2f}} {unit}<extra></extra>")
    band = [b for b in NORM_BANDS.get(key, ()) if b is not None]
    fig.update_yaxes(range=pad_range(y.values, band or (y.min(),)))
    return style(fig, height=300, title=f"{label} ({unit})")


with tabs[3]:
    groups = {}
    for key, v in fin.RATIOS.items():
        groups.setdefault(v[1], []).append(key)
    for gi, (grp, keys) in enumerate(groups.items()):
        st.subheader(grp)
        t = ratios.loc[keys].copy()
        t.insert(0, "Norm", [fin.RATIOS[k][3] for k in keys])
        t.insert(1, "Formula", [fin.RATIOS[k][2] for k in keys])
        t.index = [f"{fin.RATIOS[k][0]} ({fin.RATIOS[k][5]})" for k in keys]
        t.columns = [str(c) for c in t.columns]
        st.dataframe(t.style.format("{:,.2f}", subset=[str(y) for y in years], na_rep="–"), width="stretch")
        for start in range(0, len(keys), 3):
            row = st.columns(3)
            for col, key in zip(row, keys[start:start + 3]):
                col.plotly_chart(ratio_chart(key, C[gi]), width="stretch")

# ---------------------------------------------------------------------------
# 5. Bankruptcy risk
# ---------------------------------------------------------------------------
ZONE_COL = ["rgba(227,73,72,0.13)", "rgba(237,161,0,0.13)", "rgba(27,175,122,0.13)"]

with tabs[4]:
    st.markdown("Models from **Solvency.xlsx** (sheet *CompanyModel*). Green zone = safe, amber = grey/alert, "
                "red = distress.")
    if d.loc["personnel_costs"].isna().all():
        st.warning("Personnel costs not reported by this source, so Conan-Holder X5 is set to 0 "
                   "(score slightly optimistic). Enter it manually for exact result.")
    def z_chart(key):
        si = fin.SCORE_INFO[key]
        y = scores.loc[key]
        finite = y[np.isfinite(y)]
        lo_v = min(finite.min() if len(finite) else 0, si["zones"][0][1])
        hi_v = max(finite.max() if len(finite) else 1, si["zones"][1][1])
        span = hi_v - lo_v
        lo_v, hi_v = lo_v - span * 0.25, hi_v + span * 0.3
        fig = go.Figure()
        for (lo, hi, lab), col in zip(si["zones"], ZONE_COL):
            fig.add_hrect(y0=max(lo, lo_v), y1=min(hi, hi_v), fillcolor=col, line_width=0,
                          annotation_text=lab, annotation_position="bottom right", annotation_font_size=11)
        fig.add_scatter(x=years, y=y, mode="lines+markers+text", line=dict(color=C[0], width=2),
                        marker=dict(size=9), text=[f"{v:.2f}" if pd.notna(v) else "" for v in y],
                        textposition="top center", showlegend=False, cliponaxis=False,
                        hovertemplate="Z = %{y:.3f}<extra></extra>")
        fig.update_yaxes(range=[lo_v, hi_v])
        return style(fig, height=330, title=si["label"])

    def z_table(key):
        y = scores.loc[key]
        p = pd.DataFrame(parts[key]).T
        p.loc["Z"] = y
        p = p.map(lambda v: "–" if pd.isna(v) else f"{v:.3f}")
        p.loc["Interpretation"] = [fin.interpret(key, v) for v in y]
        p.columns = [str(c) for c in p.columns]
        return p

    models = list(fin.SCORE_INFO)
    for pair in (models[:2], models[2:]):
        # one row of charts, then one row of tables, so the two columns stay aligned
        for col, key in zip(st.columns(2), pair):
            col.plotly_chart(z_chart(key), width="stretch")
        for col, key in zip(st.columns(2), pair):
            col.dataframe(z_table(key), width="stretch", height=35 * 8 + 3)
        for col, key in zip(st.columns(2), pair):
            with col.expander(f"Formula – {fin.SCORE_INFO[key]['label']}"):
                st.code(fin.SCORE_INFO[key]["formula"], language=None)
        st.divider()
    if mode.startswith("Yahoo") and info.get("market_cap"):
        st.caption("Original Altman X4 uses market capitalisation for the latest year, book equity for earlier years.")

@st.cache_data(show_spinner="Building PDF...")
def _pdf_report(d, info, ratios, scores, parts, scale, unit):
    return report.build_report(d, info, ratios, scores, parts, scale, unit)


@st.cache_data(show_spinner="Building study guide...")
def _pdf_guide(d, info, ratios, scores, scale, unit):
    return report.build_study_guide(d, info, ratios, scores, scale, unit)


def learning_downloads(where, key):
    c1, c2 = where.columns(2)
    c1.download_button("Study guide (PDF)", _pdf_guide(d, info, ratios, scores, scale, unit_label),
                       file_name="study_guide_financial_analysis.pdf", mime="application/pdf",
                       width="stretch", key=f"guide_{key}",
                       help="Terms, formulas, meaning, worked examples on this company, solved course exercises, self-test")
    c2.download_button("Flashcards (CSV for Anki/Quizlet)", report.flashcards_csv().encode(),
                       file_name="flashcards_financial_analysis.csv", mime="text/csv", width="stretch",
                       key=f"cards_{key}")


file_base = (info.get("symbol") or info.get("name", "company")).replace(" ", "_")


# ---------------------------------------------------------------------------
# 6. Formulas explained
# ---------------------------------------------------------------------------
with tabs[5]:
    st.info("Take it offline: the study guide PDF has every term and formula, worked examples on this company's "
            "numbers, the solved course exercises and a self-test. Flashcards import into Anki or Quizlet.")
    learning_downloads(st, "learn")
    st.header("How to read the statements")
    st.markdown("""
**Balance sheet** = photo at a date (31 Dec). Left side: **assets** – what the company owns.
Right side: **liabilities + equity** – who financed those assets (creditors vs owners).
`Total assets = Total liabilities + Equity` always.

- *Current* (short-term, ST) = within 1 year. *Non-current* (long-term, LT) = after 1 year.
- Liquidity = can it pay **ST debts** with **current assets**? Solvency = can it pay **all debts** with **all assets**?

**Income statement** = film of the whole year:
```
Revenue from sales
 - Cost of sales                      = Gross profit
 - Distribution, G&A, other op. costs = Operating profit (EBIT)
 +/- Financial income / expenses      = Profit before tax
 - Income tax                         = Net profit  -> dividends or retained (unreparted) profit
```
**Cash flow statement** = real cash in/out (operating, investing, financing). Profit ≠ cash.

**Horizontal analysis** = change of each line year over year (dynamics).
**Vertical analysis** = each line as % of a total (structure).
""")
    st.header("Ratios")
    for key, (label, grp, formula, norm, meaning, unit) in fin.RATIOS.items():
        st.markdown(f"**{label}** · *{grp}*  \n`{formula}`  \nNorm: {norm}. {meaning}")
    st.header("Bankruptcy models")
    for key, si in fin.SCORE_INFO.items():
        st.markdown(f"**{si['label']}**")
        st.code(si["formula"] + "\nZones: " + "; ".join(lab + (f" < {hi}" if np.isfinite(hi) else "")
                                                         for _, hi, lab in si["zones"]), language=None)
    st.header("Other formulas from the course files")
    st.markdown(r"""
| Topic | Formula |
|---|---|
| Current yield of a bond | Annual coupon / Current price |
| Bond price | $P=\sum_{t=1}^{n}\frac{C}{(1+YTM)^t}+\frac{F}{(1+YTM)^n}$ |
| YTM (approximation) | $\frac{C+(F-P)/n}{(F+P)/2}$ |
| Future value / present value | $FV = PV(1+r)^n$, $PV = FV/(1+r)^n$ |
| Cost of equity (CAPM) | $R_e = R_f + \beta (E(R_m) - R_f)$ |
| Cost of preferred stock | $R_p = D / P_0$ |
| Sustainable growth | $g = ROE \times$ retention ratio |
| Gordon growth model | $P_0 = D_1 / (r - g)$ |
| Break-even quantity | Fixed costs / (Price − Variable cost) = FC / contribution per unit |
| P/E | Share price / EPS |
""")
    if info.get("pe") or info.get("eps"):
        st.caption(f"Live market data: price {info.get('price')}, EPS {info.get('eps')}, P/E "
                   f"{info.get('pe') and round(info['pe'], 2)}, beta {info.get('beta')}")

# ---------------------------------------------------------------------------
# 7. Export
# ---------------------------------------------------------------------------

with tabs[6]:
    st.subheader("Report")
    st.markdown("PDF with summary + automatic commentary, statements, charts, ratio tables with assessment, "
                "bankruptcy models and formula appendix.")
    st.download_button("Download PDF report", _pdf_report(d, info, ratios, scores, parts, scale, unit_label),
                       file_name=f"{file_base}_report.pdf", mime="application/pdf", type="primary")
    st.subheader("Learning")
    learning_downloads(st, "export")
    st.subheader("Data")
    st.markdown("Excel file with 3 sheets: **Data** (inputs), **Ratios** and **Bankruptcy models** – every "
                "result is a live Excel formula, so you can see/change the calculation in Excel.")
    xls = build_workbook(d, info.get("name", "Company"), f"units: {cur}")
    fname = f"{file_base}_analysis.xlsx"
    e1, e2 = st.columns(2)
    e1.download_button("Download Excel analysis", xls, file_name=fname, width="stretch",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    out = pd.concat([d / scale, ratios, scores])
    e2.download_button("Download all numbers (CSV)", out.to_csv().encode(), width="stretch",
                       file_name=fname.replace(".xlsx", ".csv"))
