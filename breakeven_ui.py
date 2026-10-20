"""Break-even & leverage tab: calculator, solver, chart, company estimate."""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import fin

PRESETS = {
    "Widgets (case study)": dict(fixed=100_000.0, price=600.0, var=500.0, qty=1_500.0),
    "Pharma drug (case study)": dict(fixed=1_500_000.0, price=201.0, var=1.0, qty=10_000.0),
    "Roof tiles (case study)": dict(fixed=100_000.0, price=1.0, var=0.99, qty=12_000_000.0),
    "Small café (example)": dict(fixed=60_000.0, price=4.5, var=1.5, qty=30_000.0),
}
GREEN, RED = "rgba(27,175,122,0.16)", "rgba(227,73,72,0.13)"


def _n(v, nd=0):
    if v is None or not np.isfinite(v):
        return "–"
    return f"{v:,.{nd}f}"


def _apply_preset():
    p = PRESETS.get(st.session_state["be_preset"])
    if p:
        for k, v in p.items():
            st.session_state[f"be_{k}"] = v


def calculator(style, C):
    st.subheader("Break-even calculator")
    st.caption("Profit = (Price − Variable cost) × Quantity − Fixed costs. Break-even is where profit = 0.")
    for k, v in PRESETS["Widgets (case study)"].items():
        st.session_state.setdefault(f"be_{k}", v)
    st.session_state.setdefault("be_target", 0.0)
    st.selectbox("Load example", list(PRESETS), key="be_preset", on_change=_apply_preset)

    c = st.columns(5)
    F = c[0].number_input("Fixed costs", min_value=0.0, step=1000.0, key="be_fixed")
    P = c[1].number_input("Price per unit", min_value=0.0, step=1.0, key="be_price", format="%.2f")
    V = c[2].number_input("Variable cost per unit", min_value=0.0, step=1.0, key="be_var", format="%.2f")
    Q = c[3].number_input("Planned quantity", min_value=0.0, step=100.0, key="be_qty")
    T = c[4].number_input("Target profit", step=1000.0, key="be_target")

    cu = P - V
    if cu <= 0:
        st.error("Price must be higher than the variable cost: each unit sold loses money, break-even impossible.")
        return
    cm = cu / P
    be_q = F / cu
    be_rev = be_q * P
    profit = cu * Q - F
    mos_q = Q - be_q
    mos_pct = mos_q / Q * 100 if Q else float("nan")
    dol = cu * Q / profit if profit else float("nan")
    q_target = fin.breakeven_units(F, P, V, T)

    k = st.columns(3) + st.columns(3)
    k[0].metric("Contribution / unit", _n(cu, 2), help="Price − Variable cost")
    k[1].metric("Contribution margin", f"{cm * 100:.1f}%", help="(Price − Variable cost) / Price")
    k[2].metric("Break-even quantity", _n(np.ceil(be_q)), help="Fixed costs / Contribution per unit")
    k[3].metric("Break-even revenue", _n(be_rev), help="Break-even quantity × Price = Fixed costs / CM ratio")
    k[4].metric("Profit at plan", _n(profit), help="Contribution per unit × Quantity − Fixed costs")
    k[5].metric("Margin of safety", f"{mos_pct:.1f}%" if np.isfinite(mos_pct) else "–",
                f"{_n(mos_q)} units", delta_color="normal" if mos_q >= 0 else "inverse",
                help="(Planned − Break-even quantity) / Planned quantity")

    # ---- chart ----
    qmax = max(be_q * 2, Q * 1.25, 1)
    q = np.linspace(0, qmax, 300)
    rev, tc = P * q, F + V * q
    fig = go.Figure()
    fig.add_scatter(x=q, y=np.minimum(rev, tc), line=dict(width=0), hoverinfo="skip", showlegend=False)
    fig.add_scatter(x=q, y=tc, fill="tonexty", fillcolor=RED, line=dict(width=0), name="Loss area",
                    hoverinfo="skip")
    fig.add_scatter(x=q, y=np.minimum(rev, tc), line=dict(width=0), hoverinfo="skip", showlegend=False)
    fig.add_scatter(x=q, y=np.maximum(rev, tc), fill="tonexty", fillcolor=GREEN, line=dict(width=0),
                    name="Profit area", hoverinfo="skip")
    fig.add_scatter(x=q, y=rev, name="Sales revenue", line=dict(color=C[0], width=2.5),
                    hovertemplate="Revenue %{y:,.0f}<extra></extra>")
    fig.add_scatter(x=q, y=tc, name="Total costs", line=dict(color=C[1], width=2.5),
                    hovertemplate="Total costs %{y:,.0f}<extra></extra>")
    fig.add_scatter(x=q, y=np.full_like(q, F), name="Fixed costs", line=dict(color="#8a8f98", width=2, dash="dash"),
                    hovertemplate="Fixed costs %{y:,.0f}<extra></extra>")
    fig.add_scatter(x=[be_q], y=[be_rev], mode="markers+text", marker=dict(size=13, color=C[0],
                    line=dict(color="white", width=2)), text=[f"Break-even<br>{_n(be_q)} units · {_n(be_rev)}"],
                    textposition="top left", showlegend=False, hovertemplate="Break-even<extra></extra>")
    if Q > 0:
        fig.add_vline(x=Q, line=dict(color="#8a8f98", width=1.5, dash="dot"))
        fig.add_annotation(x=Q, y=max(P * Q, F + V * Q) * 1.04, text=f"Plan {_n(Q)}", showarrow=False,
                           font=dict(size=11), xanchor="left")
        if Q > be_q:  # margin of safety bracket
            fig.add_shape(type="rect", x0=be_q, x1=Q, y0=0, y1=F * 0.12 + 1, line_width=0,
                          fillcolor="rgba(42,120,214,0.25)")
            fig.add_annotation(x=(be_q + Q) / 2, y=F * 0.12, yanchor="bottom", showarrow=False,
                               text=f"Margin of safety {_n(mos_q)} units ({mos_pct:.0f}%)", font=dict(size=11))
    fig = style(fig, height=470, title="Break-even chart", legend_space=80)
    # style() makes x categorical (years) - quantity axis must be numeric
    fig.update_xaxes(title_text="Quantity (units)", type="linear", tickformat=",", range=[0, qmax])
    fig.update_yaxes(title_text="Revenue / costs", tickformat=",")
    fig.update_layout(hovermode="x unified")
    st.plotly_chart(fig, width="stretch")

    st.markdown(
        f"Each unit brings **{_n(cu, 2)}** of contribution. Fixed costs of **{_n(F)}** are covered after "
        f"**{_n(be_q, 1)} units** (revenue {_n(be_rev)}). "
        + (f"At the plan of {_n(Q)} units profit is **{_n(profit)}** and sales can drop **{mos_pct:.1f}%** "
           f"before a loss." if Q and profit >= 0 else
           f"The plan of {_n(Q)} units is below break-even: loss of **{_n(-profit)}**." if Q else "")
        + (f" To earn a profit of {_n(T)} you need **{_n(np.ceil(q_target))} units**." if T else ""))

    left, right = st.columns(2, gap="large")
    with left:
        st.markdown("**Solve for the unknown** (like the case-study exercises)")
        unknown = st.radio("Find", ["Price", "Variable cost", "Fixed costs", "Quantity"], horizontal=True,
                           key="be_unknown")
        st.caption(f"Uses the other inputs and target profit = {_n(T)} (0 = break-even).")
        if unknown == "Price":
            res = V + (F + T) / Q if Q else float("nan")
            st.code(f"{_n(F + T)} = (P − {_n(V, 2)}) × {_n(Q)}\nP = {_n(V, 2)} + {_n(F + T)} / {_n(Q)} = {_n(res, 2)}",
                    language=None)
        elif unknown == "Variable cost":
            res = P - (F + T) / Q if Q else float("nan")
            st.code(f"{_n(F + T)} = ({_n(P, 2)} − V) × {_n(Q)}\nV = {_n(P, 2)} − {_n(F + T)} / {_n(Q)} = {_n(res, 4)}",
                    language=None)
        elif unknown == "Fixed costs":
            res = cu * Q - T
            st.code(f"F = ({_n(P, 2)} − {_n(V, 2)}) × {_n(Q)} − {_n(T)} = {_n(res)}\n"
                    f"Fixed costs must stay below {_n(res)} to reach the target.", language=None)
        else:
            st.code(f"Q = (F + profit) / (P − V) = ({_n(F)} + {_n(T)}) / {_n(cu, 2)} = {_n(q_target, 1)}",
                    language=None)
    with right:
        st.markdown("**Operating leverage at the plan**")
        if Q and profit > 0:
            ch = st.slider("If sales volume changes by", -50, 50, 10, 5, format="%d%%", key="be_dol_slider")
            new_profit = cu * Q * (1 + ch / 100) - F
            c1, c2 = st.columns(2)
            c1.metric("DOL", f"{dol:.2f}", help="Contribution / Operating profit = 1 / Margin of safety")
            c2.metric("Profit change", f"{(new_profit / profit - 1) * 100:+.1f}%", f"{_n(new_profit)} new profit")
            st.caption(f"DOL {dol:.2f} = 1 / margin of safety {mos_pct / 100:.3f}. A {ch:+d}% change in sales gives "
                       f"{dol * ch:+.1f}% change in profit. Close to break-even → DOL explodes → risky.")
        else:
            st.info("Plan must be above break-even to measure operating leverage.")


def company(d, scale, unit_label, style, C):
    st.subheader("This company – break-even & leverage from its statements")
    st.caption("Estimate: variable costs ≈ cost of sales, fixed costs ≈ operating expenses (distribution, G&A, R&D, "
               "other). Real split is internal information, so treat results as approximate.")
    lv = fin.leverage(d)
    years = list(d.columns)
    last = years[-1]
    if not np.isfinite(lv.at["cm_ratio", last]):
        st.info("Revenue / cost of sales not available for this company.")
        return lv

    k = st.columns(5)
    k[0].metric(f"Break-even revenue {last}", _n(lv.at["breakeven_revenue", last] / scale, 1))
    k[1].metric("Actual revenue", _n(d.at["revenue", last] / scale, 1))
    k[2].metric("Margin of safety", f"{lv.at['safety_margin', last] * 100:.1f}%")
    k[3].metric("DOL", f"{lv.at['dol', last]:.2f}")
    k[4].metric("DTL = DOL × DFL", f"{lv.at['dtl', last]:.2f}")

    c1, c2 = st.columns(2)
    fig = go.Figure()
    fig.add_bar(x=years, y=d.loc["revenue"] / scale, name="Actual revenue", marker_color=C[0],
                hovertemplate="%{y:,.1f}")
    fig.add_bar(x=years, y=lv.loc["breakeven_revenue"] / scale, name="Break-even revenue", marker_color="#9aa3ad",
                hovertemplate="%{y:,.1f}")
    c1.plotly_chart(style(fig, height=360, title=f"Revenue vs break-even ({unit_label})", legend_space=60),
                    width="stretch")
    fig = go.Figure()
    for i, (key, lab) in enumerate([("dol", "DOL"), ("dfl", "DFL"), ("dtl", "DTL")]):
        fig.add_scatter(x=years, y=lv.loc[key], name=lab, mode="lines+markers", line=dict(color=C[i], width=2),
                        marker=dict(size=8), hovertemplate="%{y:.2f}")
    c2.plotly_chart(style(fig, height=360, title="Leverage degrees (x)", legend_space=60), width="stretch")

    t = lv.copy()
    money = ["variable_costs", "fixed_costs", "contribution", "ebit", "breakeven_revenue"]
    disp = pd.DataFrame(index=[fin.LEVERAGE[i][0] for i in t.index], columns=[str(y) for y in years])
    for key in t.index:
        for y in years:
            v = t.at[key, y]
            disp.at[fin.LEVERAGE[key][0], str(y)] = (
                _n(v / scale, 1) if key in money else
                (f"{v * 100:.1f}%" if np.isfinite(v) else "–") if key in ("cm_ratio", "safety_margin") else
                (f"{v:.2f}" if np.isfinite(v) else "–"))
    disp.insert(0, "Formula", [fin.LEVERAGE[i][1] for i in t.index])
    st.dataframe(disp, width="stretch")
    st.caption("DOL from yearly changes is unstable when revenue barely moves (dividing by a number close to 0) – "
               "prefer the contribution-based DOL.")
    return lv


def render(d, scale, unit_label, style, C):
    calculator(style, C)
    st.divider()
    company(d, scale, unit_label, style, C)
    with st.expander("Formulas – break-even, margin of safety, leverage"):
        st.code("""Contribution per unit        = Price − Variable cost per unit
Contribution margin ratio    = Contribution per unit / Price
Break-even quantity          = Fixed costs / Contribution per unit
Break-even revenue           = Fixed costs / Contribution margin ratio
Units for target profit      = (Fixed costs + Target profit) / Contribution per unit
Margin of safety (units)     = Actual units − Break-even units
Margin of safety (%)         = (Actual sales − Break-even sales) / Actual sales × 100
DOL (operating leverage)     = Contribution / EBIT = %ΔEBIT / %ΔSales = 1 / Margin of safety %
DFL (financial leverage)     = EBIT / (EBIT − Interest) = %ΔEBT / %ΔEBIT
DTL (total leverage)         = DOL × DFL""", language=None)
