"""Standalone calculators: no company needed, type only the inputs each tool needs."""
from __future__ import annotations

import html

import numpy as np
import pandas as pd
import streamlit as st

import breakeven_ui
import dupont_ui
import fin

CSS = """<style>
.tl-grid {display:grid; grid-template-columns:repeat(auto-fill, minmax(230px, 1fr)); gap:12px; margin:6px 0 10px;}
.tl-card {border:1px solid rgba(128,128,128,.25); border-radius:14px; padding:12px 14px; background:rgba(128,128,128,.05);}
.tl-label {font-size:.76rem; opacity:.72; text-transform:uppercase; letter-spacing:.02em;}
.tl-val {font-size:1.6rem; font-weight:650; line-height:1.3;}
.tl-f {font-size:.74rem; opacity:.65; line-height:1.35; font-family:ui-monospace, Menlo, monospace;}
.tl-badge {display:inline-block; font-size:.72rem; font-weight:600; border-radius:999px; padding:1px 9px; margin-top:6px;}
.tl-good {background:rgba(27,175,122,.16); color:#13845b;} .tl-warn {background:rgba(237,161,0,.18); color:#a06c00;}
.tl-bad {background:rgba(227,73,72,.15); color:#c03534;} .tl-info {background:rgba(42,120,214,.13); color:#2a78d6;}
</style>"""


def n(v, nd=2):
    if v is None or not np.isfinite(v):
        return "–"
    return f"{v:,.{nd}f}"


def div(a, b):
    return a / b if b else float("nan")


def cards(items):
    """items: (label, value_text, formula_with_numbers, badge_text, badge_kind)"""
    out = "<div class='tl-grid'>"
    for label, val, formula, badge, kind in items:
        b = f"<span class='tl-badge tl-{kind}'>{html.escape(badge)}</span>" if badge else ""
        out += (f"<div class='tl-card'><div class='tl-label'>{html.escape(label)}</div><div class='tl-val'>{val}</div>"
                f"<div class='tl-f'>{html.escape(formula)}</div>{b}</div>")
    st.markdown(out + "</div>", unsafe_allow_html=True)


def inputs(spec, key, ncols=4):
    """spec: list of (name, label, default, help). Returns dict of values."""
    vals = {}
    cols = st.columns(ncols)
    for i, (name, label, default, hlp) in enumerate(spec):
        vals[name] = cols[i % ncols].number_input(label, value=float(default), key=f"{key}_{name}", help=hlp,
                                                  format="%.4f" if abs(default) < 1 and default else "%.2f")
    return vals


def band(v, lo=None, hi=None):
    if not np.isfinite(v):
        return "", "info"
    if lo is not None and v < lo:
        return "below norm", "bad"
    if hi is not None and v > hi:
        return "above norm", "warn"
    return "within norm", "good"


# ---------------------------------------------------------------------------
def t_liquidity():
    v = inputs([("cash", "Cash", 50, None), ("sti", "ST investments", 20, None),
                ("rec", "Receivables (ST)", 200, None), ("ca", "Current assets", 450, None),
                ("cl", "Current liabilities (ST debt)", 300, None)], "liq", 5)
    a = div(v["cash"], v["cl"])
    q = div(v["cash"] + v["sti"] + v["rec"], v["cl"])
    c = div(v["ca"], v["cl"])
    cards([("Absolute liquidity", n(a), f"{n(v['cash'])} / {n(v['cl'])}  (norm 0.2–0.25)", *band(a, .2, .25)),
           ("Intermediary (quick) liquidity", n(q), f"({n(v['cash'])} + {n(v['sti'])} + {n(v['rec'])}) / {n(v['cl'])}"
            "  (norm 0.7–0.8)", *band(q, .7, .8)),
           ("Current liquidity", n(c), f"{n(v['ca'])} / {n(v['cl'])}  (norm 2–2.5)", *band(c, 2, 2.5)),
           ("Working capital", n(v["ca"] - v["cl"]), f"{n(v['ca'])} − {n(v['cl'])}",
            "positive" if v["ca"] >= v["cl"] else "negative", "good" if v["ca"] >= v["cl"] else "bad")])


def t_solvency():
    v = inputs([("ta", "Total assets", 1200, None), ("st", "ST debt", 300, None), ("lt", "LT debt", 400, None),
                ("eq", "Equity", 500, "Leave as Total assets − debts if unsure"),
                ("ebit", "Operating profit (EBIT)", 150, None), ("int", "Interest expense", 25, None)], "sol", 3)
    debts = v["st"] + v["lt"]
    gs, dr, de, ic = div(v["ta"], debts), div(debts, v["ta"]), div(debts, v["eq"]), div(v["ebit"], v["int"])
    cards([("General solvency", n(gs), f"{n(v['ta'])} / ({n(v['st'])} + {n(v['lt'])})",
            *(("insolvent", "bad") if gs < 1 else ("acceptable", "warn") if gs < 2 else ("good", "good"))),
           ("Total debt ratio", n(dr), f"{n(debts)} / {n(v['ta'])}",
            *(("high debt", "bad") if dr > .6 else ("moderate", "warn") if dr > .5 else ("good", "good"))),
           ("Debt to equity", n(de), f"{n(debts)} / {n(v['eq'])}",
            *(("high leverage", "bad") if de > 1.5 else ("moderate", "warn") if de > 1 else ("good", "good"))),
           ("Equity ratio", n(div(v["eq"], v["ta"])), f"{n(v['eq'])} / {n(v['ta'])}", "", "info"),
           ("Interest coverage", n(ic), f"{n(v['ebit'])} / {n(v['int'])}",
            *(("risky", "bad") if ic < 1.5 else ("acceptable", "warn") if ic < 3 else ("good", "good")))])


def t_profitability():
    v = inputs([("rev", "Revenue", 2300, None), ("gp", "Gross profit", 550, None),
                ("pbt", "Profit before tax", 190, None), ("np", "Net profit", 160, None),
                ("ta0", "Total assets – start of year", 1300, "Previous year-end. Same as end if unknown."),
                ("ta1", "Total assets – end of year", 1400, None), ("eq", "Equity", 550, None)], "prof", 4)
    avg = (v["ta0"] + v["ta1"]) / 2
    cards([("Return on sales", n(div(v["pbt"], v["rev"]) * 100) + "%", f"{n(v['pbt'])} / {n(v['rev'])} × 100", "", "info"),
           ("Gross profit %", n(div(v["gp"], v["rev"]) * 100) + "%", f"{n(v['gp'])} / {n(v['rev'])} × 100", "", "info"),
           ("Net profit margin", n(div(v["np"], v["rev"]) * 100) + "%", f"{n(v['np'])} / {n(v['rev'])} × 100", "", "info"),
           ("Return on assets", n(div(v["pbt"], avg) * 100) + "%",
            f"{n(v['pbt'])} / (({n(v['ta0'])} + {n(v['ta1'])}) / 2) × 100", "", "info"),
           ("Return on equity", n(div(v["np"], v["eq"]) * 100) + "%", f"{n(v['np'])} / {n(v['eq'])} × 100", "", "info"),
           ("Asset turnover", n(div(v["rev"], v["ta1"])), f"{n(v['rev'])} / {n(v['ta1'])}", "", "info")])


def t_dupont():
    v = inputs([("np", "Net profit", 160, None), ("pbt", "Profit before tax", 190, None),
                ("int", "Interest expense", 25, "0 if no debt"), ("rev", "Revenue", 2300, None),
                ("ta", "Total assets", 1400, None), ("eq", "Equity", 550, None)], "dup", 3)
    d = pd.DataFrame({"Now": {"net_profit": v["np"], "pretax_profit": v["pbt"], "financial_expenses": v["int"],
                              "revenue": v["rev"], "total_assets": v["ta"], "equity": v["eq"]}})
    dp = fin.dupont(d)
    st.markdown(dupont_ui.CSS, unsafe_allow_html=True)
    tree = {"roe": ["roa", "equity_multiplier"], "roa": ["net_margin", "asset_turnover"],
            "net_margin": ["tax_burden", "interest_burden", "ebit_margin"]}
    st.markdown(f"<div class='dp-wrap'>{dupont_ui.node('roe', tree, (dp, d, 'Now', None, 1))}</div>",
                unsafe_allow_html=True)
    st.caption("ROE = Tax burden × Interest burden × EBIT margin × Asset turnover × Equity multiplier. "
               "EBIT = profit before tax + interest.")


def t_zscore():
    v = inputs([("ta", "Total assets", 1400, None), ("ca", "Current assets", 560, None),
                ("inv", "Inventories", 170, None), ("cl", "ST debt (current liabilities)", 380, None),
                ("ncl", "LT debt", 350, None), ("eq", "Equity", 670, None),
                ("re", "Retained earnings", 170, None), ("rev", "Sales", 2300, None),
                ("gp", "Gross profit", 550, None), ("ebit", "Operating profit (EBIT)", 210, None),
                ("pbt", "Profit before tax", 190, None), ("ebitda", "EBITDA", 280, None),
                ("fin", "Financial expenses", 25, None), ("pers", "Personnel costs", 450, "0 if unknown")], "z", 4)
    keys = dict(total_assets="ta", current_assets="ca", inventory="inv", current_liabilities="cl",
                noncurrent_liabilities="ncl", equity="eq", retained_earnings="re", revenue="rev", gross_profit="gp",
                operating_profit="ebit", pretax_profit="pbt", ebitda="ebitda", financial_expenses="fin",
                personnel_costs="pers")
    d = pd.DataFrame({"Now": {k: v[s] for k, s in keys.items()}}).reindex(list(fin.INPUTS))
    scores, _ = fin.compute_scores(d)
    kind = {"DISTRESS": "bad", "HIGH": "bad", "DANGER": "bad", "SOLVENT": "good", "SAFE": "good", "LOW": "good",
            "GOOD": "good"}
    items = []
    for k, si in fin.SCORE_INFO.items():
        z = scores.at[k, "Now"]
        lab = fin.interpret(k, z)
        items.append((si["label"], n(z, 3), si["formula"].split("\n")[0], lab, kind.get(lab.split()[0], "warn")))
    cards(items)
    with st.expander("All formulas"):
        for si in fin.SCORE_INFO.values():
            st.code(si["label"] + "\n" + si["formula"], language=None)


def _bond_price(face, rate, ytm, years, m):
    c, r, k = face * rate / m, ytm / m, int(round(years * m))
    if r == 0:
        return c * k + face
    return c * (1 - (1 + r) ** -k) / r + face / (1 + r) ** k


def t_bonds():
    c = st.columns(5)
    face = c[0].number_input("Face (par) value", value=1000.0, key="b_face")
    rate = c[1].number_input("Coupon rate, %", value=8.0, key="b_rate") / 100
    years = c[2].number_input("Years to maturity", value=15.0, min_value=0.5, key="b_years")
    m = {"Annual": 1, "Semiannual": 2, "Quarterly": 4}[c[3].selectbox("Coupons paid", ["Annual", "Semiannual",
                                                                                          "Quarterly"], key="b_m")]
    mode = c[4].radio("I know the", ["Yield (find price)", "Price (find yield)"], key="b_mode")
    c2 = st.columns(5)
    if mode.startswith("Yield"):
        ytm = c2[0].number_input("Market yield / YTM, %", value=10.0, key="b_ytm") / 100
        price = _bond_price(face, rate, ytm, years, m)
    else:
        price = c2[0].number_input("Current price", value=928.09, key="b_price")
        lo, hi = -0.99, 5.0  # bisection: price falls as yield rises
        for _ in range(200):
            mid = (lo + hi) / 2
            lo, hi = (mid, hi) if _bond_price(face, rate, mid, years, m) > price else (lo, mid)
        ytm = (lo + hi) / 2
    coupon = face * rate
    approx = div(coupon + (face - price) / years, (face + price) / 2)
    status = ("discount (price < par, YTM > coupon)" if price < face - 1e-6 else
              "premium (price > par, YTM < coupon)" if price > face + 1e-6 else "at par")
    cards([("Bond price", n(price), f"C×[1−(1+r)^−n]/r + F/(1+r)^n, r={ytm / m:.4%}, n={int(years * m)}",
            status, "info"),
           ("Yield to maturity", f"{ytm * 100:.2f}%", "rate that makes PV of cash flows = price", "", "info"),
           ("Current yield", f"{div(coupon, price) * 100:.2f}%", f"{n(coupon)} / {n(price)}", "", "info"),
           ("YTM approximation", f"{approx * 100:.2f}%", "(C + (F − P)/n) / ((F + P)/2)", "", "info")])


def t_tvm():
    c = st.columns(4)
    direction = c[0].radio("Find", ["Future value", "Present value"], key="tvm_dir")
    amount = c[1].number_input("Present value" if direction == "Future value" else "Future value",
                               value=5000.0, key="tvm_amt")
    r = c[2].number_input("Annual interest rate, %", value=7.0, key="tvm_r") / 100
    yrs = c[3].number_input("Years", value=5.0, key="tvm_n")
    m = {"Annually": 1, "Semiannually": 2, "Quarterly": 4, "Monthly": 12}[
        st.select_slider("Compounding", ["Annually", "Semiannually", "Quarterly", "Monthly"], key="tvm_m")]
    f = (1 + r / m) ** (m * yrs)
    res = amount * f if direction == "Future value" else amount / f
    cards([(direction, n(res), (f"{n(amount)} × (1 + {r:.2%}/{m})^({m}×{yrs:g})" if direction == "Future value" else
                                f"{n(amount)} / (1 + {r:.2%}/{m})^({m}×{yrs:g})"), "", "info"),
           ("Growth factor", n(f, 4), f"(1 + r/m)^(m×n)", "", "info"),
           ("Interest earned", n(abs(res - amount)), "difference", "", "info")])


def t_cost_of_capital():
    st.markdown("**Cost of equity (CAPM), cost of preferred, WACC**")
    v = inputs([("rf", "Risk-free rate, %", 4.2, None), ("beta", "Beta", 1.24, None),
                ("mrp", "Market risk premium (Rm − Rf), %", 8.0, None), ("pd", "Preferred dividend", 9.0, None),
                ("pp", "Preferred price", 64.0, None), ("rd", "Cost of debt (interest rate), %", 7.0, None),
                ("tax", "Tax rate, %", 12.0, None), ("E", "Equity value", 600.0, None),
                ("D", "Debt value", 400.0, None)], "coc", 3)
    re = v["rf"] + v["beta"] * v["mrp"]
    rp = div(v["pd"], v["pp"]) * 100
    w = div(v["E"], v["E"] + v["D"])
    wacc = w * re + (1 - w) * v["rd"] * (1 - v["tax"] / 100)
    cards([("Cost of equity (CAPM)", f"{re:.2f}%", f"{v['rf']}% + {v['beta']} × {v['mrp']}%", "", "info"),
           ("Cost of preferred", f"{rp:.2f}%", f"{n(v['pd'])} / {n(v['pp'])}", "", "info"),
           ("After-tax cost of debt", f"{v['rd'] * (1 - v['tax'] / 100):.2f}%", f"{v['rd']}% × (1 − {v['tax']}%)", "", "info"),
           ("WACC", f"{wacc:.2f}%", f"{w:.0%} × {re:.2f}% + {1 - w:.0%} × {v['rd']}% × (1 − {v['tax']}%)", "", "info")])


def t_dividends():
    v = inputs([("roe", "ROE, %", 12.0, None), ("payout", "Payout ratio, %", 40.0, None),
                ("d1", "Dividend next year (D1)", 4.0, None), ("r", "Required return, %", 10.0, None),
                ("g", "Constant growth g, %", 7.0, None)], "div", 5)
    g_s = v["roe"] * (1 - v["payout"] / 100)
    price = div(v["d1"], (v["r"] - v["g"]) / 100) if v["r"] > v["g"] else float("nan")
    st.markdown("**Two-stage model** – fast growth for some years, then constant growth")
    w = inputs([("d0", "Dividend paid now (D0)", 2.0, None), ("g1", "Growth stage 1, %", 15.0, None),
                ("n1", "Years of stage 1", 5.0, None), ("g2", "Growth after, %", 5.0, None),
                ("r2", "Required return, %", 10.0, None)], "two", 5)
    k, r2, g1, g2 = int(w["n1"]), w["r2"] / 100, w["g1"] / 100, w["g2"] / 100
    pv1 = sum(w["d0"] * (1 + g1) ** t / (1 + r2) ** t for t in range(1, k + 1))
    dk1 = w["d0"] * (1 + g1) ** k * (1 + g2)
    tv = div(dk1, r2 - g2) if r2 > g2 else float("nan")
    p2 = pv1 + tv / (1 + r2) ** k
    cards([("Sustainable growth g", f"{g_s:.2f}%", f"{v['roe']}% × (1 − {v['payout']}%)", "", "info"),
           ("Gordon price", n(price), f"{n(v['d1'])} / ({v['r']}% − {v['g']}%)",
            "" if np.isfinite(price) else "needs r > g", "info" if np.isfinite(price) else "bad"),
           ("Two-stage price", n(p2), f"PV dividends 1–{k}: {n(pv1)} + PV terminal: {n(tv / (1 + r2) ** k)}", "", "info"),
           ("Terminal value (year " + str(k) + ")", n(tv), f"D{k + 1} {n(dk1)} / ({w['r2']}% − {w['g2']}%)", "", "info")])


def t_leverage():
    v = inputs([("sales", "Sales", 1_000_000, None), ("var", "Variable costs", 600_000, None),
                ("fixed", "Fixed costs", 250_000, None), ("int", "Interest expense", 50_000, None)], "lev", 4)
    contrib = v["sales"] - v["var"]
    ebit = contrib - v["fixed"]
    dol, dfl = div(contrib, ebit), div(ebit, ebit - v["int"])
    cm = div(contrib, v["sales"])
    be = div(v["fixed"], cm)
    mos = div(v["sales"] - be, v["sales"])
    cards([("Contribution", n(contrib, 0), f"{n(v['sales'], 0)} − {n(v['var'], 0)}", "", "info"),
           ("EBIT", n(ebit, 0), f"{n(contrib, 0)} − {n(v['fixed'], 0)}", "loss" if ebit < 0 else "", "bad" if ebit < 0 else "info"),
           ("Break-even sales", n(be, 0), f"{n(v['fixed'], 0)} / {cm:.2%}", "", "info"),
           ("Margin of safety", f"{mos * 100:.1f}%", f"({n(v['sales'], 0)} − {n(be, 0)}) / {n(v['sales'], 0)}",
            *(("risky", "bad") if mos < .1 else ("thin", "warn") if mos < .3 else ("comfortable", "good"))),
           ("DOL", n(dol), f"{n(contrib, 0)} / {n(ebit, 0)} = 1 / MoS", "", "info"),
           ("DFL", n(dfl), f"{n(ebit, 0)} / ({n(ebit, 0)} − {n(v['int'], 0)})", "", "info"),
           ("DTL", n(dol * dfl), f"{n(dol)} × {n(dfl)}", "", "info")])
    ch = st.slider("Sales change", -30, 30, 10, 5, format="%d%%", key="lev_ch")
    st.markdown(f"Sales {ch:+d}% → EBIT **{dol * ch:+.1f}%** → profit before tax **{dol * dfl * ch:+.1f}%**")


TOOLS = {
    "Break-even & margin of safety": lambda style, C: breakeven_ui.calculator(style, C),
    "Operating & financial leverage": lambda style, C: t_leverage(),
    "Liquidity ratios": lambda style, C: t_liquidity(),
    "Solvency & debt": lambda style, C: t_solvency(),
    "Profitability ratios": lambda style, C: t_profitability(),
    "DuPont ROE": lambda style, C: t_dupont(),
    "Bankruptcy Z-scores": lambda style, C: t_zscore(),
    "Bond price & yield": lambda style, C: t_bonds(),
    "Time value of money": lambda style, C: t_tvm(),
    "Cost of capital (CAPM, WACC)": lambda style, C: t_cost_of_capital(),
    "Dividend valuation (Gordon, two-stage)": lambda style, C: t_dividends(),
}


def render(style, C):
    st.markdown(CSS, unsafe_allow_html=True)
    st.title("Financial calculators")
    st.caption("No company needed – type only the numbers each tool asks for. Example values are pre-filled; "
               "replace them with yours. Results update instantly.")
    tool = st.sidebar.radio("Tool", list(TOOLS), key="tool_pick")
    st.header(tool)
    TOOLS[tool](style, C)
