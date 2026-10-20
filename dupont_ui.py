"""Interactive DuPont analysis tab."""
from __future__ import annotations

import html

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

import fin

PCT = {"ebit_margin", "net_margin", "roa", "roe"}
# numerator, denominator rows for each factor (rows of the input data or of the dupont frame)
PARTS = {
    "tax_burden": ("net_profit", "pretax_profit"), "interest_burden": ("pretax_profit", "ebit"),
    "ebit_margin": ("ebit", "revenue"), "net_margin": ("net_profit", "revenue"),
    "asset_turnover": ("revenue", "assets_used"), "roa": ("net_profit", "assets_used"),
    "equity_multiplier": ("assets_used", "equity_used"), "roe": ("net_profit", "equity_used"),
}
NAMES = {"net_profit": "Net profit", "pretax_profit": "Profit before tax", "ebit": "EBIT", "revenue": "Revenue",
         "assets_used": "Total assets", "equity_used": "Equity"}

CSS = """<style>
.dp-wrap {overflow-x:auto; padding:6px 0 4px;}
.dp-node {display:flex; flex-direction:column; align-items:center;}
.dp-row {display:flex; align-items:flex-start; justify-content:center; gap:10px;}
.dp-op {align-self:flex-start; margin-top:38px; font-size:1.3rem; opacity:.45; font-weight:300;}
.dp-link {width:2px; height:20px; background:rgba(128,128,128,.35);}
.dp-card {border:1px solid rgba(128,128,128,.25); border-radius:14px; padding:12px 16px 10px; min-width:160px;
          max-width:220px; background:rgba(128,128,128,.05); text-align:center;}
.dp-card.l0 {border:2px solid #2a78d6; background:rgba(42,120,214,.08); min-width:230px;}
.dp-card.l1 {border-color:rgba(42,120,214,.45);}
.dp-label {font-size:.78rem; opacity:.72; letter-spacing:.02em; text-transform:uppercase;}
.dp-val {font-size:1.65rem; font-weight:650; line-height:1.25; margin:2px 0;}
.dp-card.l0 .dp-val {font-size:2.2rem;}
.dp-formula {font-size:.74rem; opacity:.62; line-height:1.3;}
.dp-delta {font-size:.78rem; font-weight:600; margin-top:4px;}
.dp-up {color:#1a9e6e;} .dp-down {color:#e34948;} .dp-flat {opacity:.55;}
</style>"""


def fmt(key, v, signed=False):
    if v is None or not np.isfinite(v):
        return "–"
    s = "+" if signed and v > 0 else ""
    return f"{s}{v * 100:.1f}%" if key in PCT else f"{s}{v:.2f}x"


def _num(v, scale):
    return "–" if v is None or not np.isfinite(v) else f"{v / scale:,.1f}"


def card(key, dp, d, year, prev, scale, level):
    v = dp.at[key, year]
    num, den = PARTS[key]
    src = lambda k, y: dp.at[k, y] if k in dp.index and k not in ("net_profit", "pretax_profit", "revenue") \
        else d.at[k, y]  # noqa: E731
    formula = f"{NAMES[num]} / {NAMES[den]}<br>{_num(src(num, year), scale)} / {_num(src(den, year), scale)}"
    delta = ""
    if prev is not None:
        pv = dp.at[key, prev]
        if np.isfinite(v) and np.isfinite(pv):
            ch = v - pv
            if abs(ch) < 1e-9:
                delta = f"<div class='dp-delta dp-flat'>= vs {prev}</div>"
            else:
                # equity multiplier up raises ROE but also risk -> neutral colour
                cls = "dp-flat" if key == "equity_multiplier" else ("dp-up" if ch > 0 else "dp-down")
                arrow = "▲" if ch > 0 else "▼"
                txt = f"{ch * 100:+.1f} pp" if key in PCT else f"{ch:+.2f}x"
                delta = f"<div class='dp-delta {cls}'>{arrow} {txt} vs {prev}</div>"
    label = html.escape(fin.DUPONT[key][0])
    return (f"<div class='dp-card l{level}' title='{html.escape(fin.DUPONT[key][2])}'>"
            f"<div class='dp-label'>{label}</div><div class='dp-val'>{fmt(key, v)}</div>"
            f"<div class='dp-formula'>{formula}</div>{delta}</div>")


def node(key, tree, args, level=0):
    children = tree.get(key, [])
    h = f"<div class='dp-node'>{card(key, *args, level)}"
    if children:
        parts = [node(c, tree, args, level + 1) for c in children]
        h += "<div class='dp-link'></div><div class='dp-row'>" + "<div class='dp-op'>×</div>".join(parts) + "</div>"
    return h + "</div>"


def render(d, info, scale, unit_label, style, C, load_fn, is_yahoo):
    st.markdown(CSS, unsafe_allow_html=True)
    years = list(d.columns)
    c1, c2, c3 = st.columns([2, 2, 1.4])
    model = c1.radio("Model", ["3-step", "5-step"], horizontal=True, index=1,
                     help="3-step: ROE = Net margin × Asset turnover × Equity multiplier. "
                          "5-step splits net margin into Tax burden × Interest burden × EBIT margin.")
    year = c2.select_slider("Year", options=years, value=years[-1])
    average = c3.toggle("Average balances", value=False,
                        help="Use (start + end of year) / 2 for assets and equity, as in the ROA formula of the course. "
                             "First year falls back to year-end.")
    dp = fin.dupont(d, average=average)
    factors = fin.DUPONT_5 if model == "5-step" else fin.DUPONT_3
    prev = years[years.index(year) - 1] if years.index(year) > 0 else None

    if not np.isfinite(dp.at["roe", year]):
        st.warning("Not enough data for DuPont in this year (need net profit, revenue, total assets, equity).")
        return
    if d.at["equity", year] <= 0:
        st.error("Equity is negative: ROE and the equity multiplier have no economic meaning "
                 "(owners have no positive capital). Look at ROA instead.")
    if d.at["pretax_profit", year] <= 0:
        st.warning("Profit before tax is negative, so tax and interest burden are hard to interpret.")

    # ---- tree -----------------------------------------------------------
    tree = ({"roe": ["roa", "equity_multiplier"], "roa": ["net_margin", "asset_turnover"],
             "net_margin": ["tax_burden", "interest_burden", "ebit_margin"]}
            if model == "5-step" else {"roe": ["net_margin", "asset_turnover", "equity_multiplier"]})
    st.markdown(f"<div class='dp-wrap'>{node('roe', tree, (dp, d, year, prev, scale))}</div>",
                unsafe_allow_html=True)
    eq = " × ".join(f"{fin.DUPONT[f][0]} {fmt(f, dp.at[f, year])}" for f in factors)
    st.caption(f"{year}: ROE = {eq} = **{fmt('roe', dp.at['roe', year])}** · figures in {unit_label}. "
               "EBIT = profit before tax + interest expense. Hover a card for its meaning.")

    st.divider()
    left, right = st.columns([1, 1], gap="large")

    # ---- what-if ----------------------------------------------------------
    with left:
        st.subheader("What-if simulator")
        st.caption("Move a driver and see ROE react. ROE is a product, so +10% in any factor = +10% ROE.")
        base = [float(dp.at[f, year]) for f in factors]
        kp = f"{info.get('symbol', info.get('name'))}_{year}_{model}_{average}"
        if st.button("Reset", key=f"reset_{kp}"):
            for f in factors:
                st.session_state[f"wi_{kp}_{f}"] = 0
        new = []
        for f, b in zip(factors, base):
            ch = st.slider(f"{fin.DUPONT[f][0]} (now {fmt(f, b)})", -50, 50, 0, 5, format="%d%%",
                           key=f"wi_{kp}_{f}")
            new.append(b * (1 + ch / 100))
        roe_new = float(np.prod(new))
        m1, m2 = st.columns(2)
        m1.metric("Actual ROE", fmt("roe", float(np.prod(base))))
        m2.metric("Scenario ROE", fmt("roe", roe_new), fmt("roe", roe_new - float(np.prod(base)), signed=True)
                  .replace("%", " pp"))

        st.markdown("**Target solver** – what must change to reach a target ROE?")
        t1, t2 = st.columns(2)
        target = t1.number_input("Target ROE, %", value=round(float(np.prod(base)) * 100 + 5, 1), step=1.0)
        lever = t2.selectbox("Change only", factors, format_func=lambda f: fin.DUPONT[f][0])
        i = factors.index(lever)
        others = float(np.prod([b for j, b in enumerate(base) if j != i]))
        if others and np.isfinite(others):
            need = target / 100 / others
            st.info(f"{fin.DUPONT[lever][0]} must go from **{fmt(lever, base[i])}** to **{fmt(lever, need)}** "
                    f"({(need / base[i] - 1) * 100:+.1f}%), other drivers unchanged.")

    # ---- chain substitution waterfall ---------------------------------
    with right:
        st.subheader("Why did ROE change?")
        st.caption("Factor analysis by chain substitution: replace one factor at a time (from year A to year B) "
                   "and measure the ROE change each replacement causes. Contributions add up exactly.")
        if len(years) < 2:
            st.info("Need at least 2 years.")
        else:
            a1, a2 = st.columns(2)
            ya = a1.selectbox("From year", years[:-1], index=max(0, years.index(year) - 1) if year != years[0] else 0)
            yb = a2.selectbox("To year", [y for y in years if y > ya], index=0 if year <= ya else
                              [y for y in years if y > ya].index(year))
            b0 = [float(dp.at[f, ya]) for f in factors]
            b1 = [float(dp.at[f, yb]) for f in factors]
            if all(np.isfinite(b0 + b1)):
                contrib = fin.chain_substitution(b0, b1)
                roe_a, roe_b = float(np.prod(b0)), float(np.prod(b1))
                fig = go.Figure(go.Waterfall(
                    x=[f"ROE {ya}"] + [fin.DUPONT[f][0] for f in factors] + [f"ROE {yb}"],
                    y=[roe_a * 100] + [c * 100 for c in contrib] + [roe_b * 100],
                    measure=["absolute"] + ["relative"] * len(factors) + ["total"],
                    text=[f"{roe_a * 100:.1f}%"] + [f"{c * 100:+.1f}" for c in contrib] + [f"{roe_b * 100:.1f}%"],
                    textposition="outside", cliponaxis=False,
                    connector=dict(line=dict(color="rgba(128,128,128,0.4)", width=1)),
                    increasing=dict(marker=dict(color=C[2])), decreasing=dict(marker=dict(color=C[7])),
                    totals=dict(marker=dict(color=C[0])),
                    hovertemplate="%{x}: %{y:.2f}<extra></extra>"))
                lo = min(0, *(np.cumsum([roe_a] + contrib) * 100))
                hi = max(np.cumsum([roe_a] + contrib) * 100.0)
                fig.update_yaxes(title_text="ROE, % / percentage points", range=[lo * 1.15, hi * 1.18])
                fig.update_layout(showlegend=False)
                st.plotly_chart(style(fig, height=380), width="stretch")
                tab = pd.DataFrame({
                    "Factor": [fin.DUPONT[f][0] for f in factors],
                    str(ya): [fmt(f, v) for f, v in zip(factors, b0)],
                    str(yb): [fmt(f, v) for f, v in zip(factors, b1)],
                    "Effect on ROE, pp": [f"{c * 100:+.2f}" for c in contrib],
                })
                st.dataframe(tab, hide_index=True, width="stretch")
                biggest = factors[int(np.argmax(np.abs(contrib)))]
                st.markdown(f"ROE moved **{(roe_b - roe_a) * 100:+.1f} pp** ({roe_a * 100:.1f}% → {roe_b * 100:.1f}%). "
                            f"Main driver: **{fin.DUPONT[biggest][0]}** "
                            f"({contrib[factors.index(biggest)] * 100:+.1f} pp).")
            else:
                st.info("Missing data in one of the years.")

    st.divider()

    # ---- trend ------------------------------------------------------------
    st.subheader("Trend of the drivers")
    keys = ["roe", "roa"] + factors
    for start in range(0, len(keys), 4):
        for col, k in zip(st.columns(4), keys[start:start + 4]):
            y = dp.loc[k] * (100 if k in PCT else 1)
            fig = go.Figure(go.Scatter(x=years, y=y, mode="lines+markers+text", line=dict(color=C[0], width=2),
                                       marker=dict(size=8), text=[fmt(k, v) for v in dp.loc[k]],
                                       textposition="top center", cliponaxis=False,
                                       hovertemplate="%{y:.2f}<extra></extra>"))
            v = y[np.isfinite(y)]
            if len(v):
                span = (v.max() - v.min()) or abs(v.max()) or 1
                fig.update_yaxes(range=[v.min() - span * 0.2, v.max() + span * 0.35])
            col.plotly_chart(style(fig, height=230, title=fin.DUPONT[k][0]), width="stretch",
                             config={"displayModeBar": False})

    # ---- peers --------------------------------------------------------
    st.subheader("Compare with other companies")
    st.caption("Latest fiscal year of each company, 3-step DuPont, year-end balances. Up to 5 tickers.")
    peers_txt = st.text_input("Tickers, comma separated", placeholder="e.g. MSFT, GOOGL, 005930.KS",
                              key="dp_peers")
    rows = []
    me = info.get("symbol") or info.get("name", "This company")
    d_me = fin.dupont(d)
    rows.append((me, d_me[years[-1]], years[-1]))
    errors = []
    for t in [t.strip().upper() for t in peers_txt.split(",") if t.strip()][:5]:
        try:
            pdata, _ = load_fn(t)
            pdp = fin.dupont(fin.fill_derived(pdata))
            rows.append((t, pdp[pdp.columns[-1]], pdp.columns[-1]))
        except Exception as e:  # noqa: BLE001
            errors.append(f"{t}: {e}")
    for e in errors:
        st.warning(e)
    if len(rows) > 1:
        comp = ["net_margin", "asset_turnover", "equity_multiplier", "roe"]
        names = [f"{n} ({y})" for n, _, y in rows]
        fig = make_subplots(rows=1, cols=4, subplot_titles=[fin.DUPONT[k][0] for k in comp], shared_yaxes=True,
                            horizontal_spacing=0.04)
        colors = [C[0]] + ["#9aa3ad"] * (len(rows) - 1)
        for i, k in enumerate(comp, 1):
            vals = [s[k] * (100 if k in PCT else 1) for _, s, _ in rows]
            fig.add_bar(y=names, x=vals, orientation="h", marker_color=colors, showlegend=False,
                        text=[fmt(k, s[k]) for _, s, _ in rows], textposition="outside", cliponaxis=False,
                        hovertemplate="%{y}: %{x:.2f}<extra></extra>", row=1, col=i)
            fv = [v for v in vals if np.isfinite(v)]
            if fv:  # headroom so the value label after the longest bar is not cut
                fig.update_xaxes(range=[min(0, min(fv)) * 1.4, max(0, max(fv)) * 1.45 or 1], row=1, col=i)
        fig.update_yaxes(autorange="reversed", type="category")
        fig.update_xaxes(showgrid=False, showticklabels=False, zeroline=True)
        fig = style(fig, height=110 + 48 * len(rows))
        fig.update_yaxes(type="category")
        fig.update_xaxes(type="linear")
        st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
        best = max(rows, key=lambda r: r[1]["roe"] if np.isfinite(r[1]["roe"]) else -np.inf)
        st.caption(f"Highest ROE: {best[0]} ({fmt('roe', best[1]['roe'])}). Same ROE can come from different "
                   "routes: high margins (luxury, software), fast asset turnover (retail) or high leverage (banks).")
    elif not is_yahoo:
        st.caption("Peers are loaded from Yahoo Finance.")
