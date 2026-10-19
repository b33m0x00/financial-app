"""PDF exports: company analysis report + study guide (terms, formulas, worked examples, quiz)."""
from __future__ import annotations

import io
import math
import re
from datetime import date

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from reportlab.lib import colors  # noqa: E402
from reportlab.lib.enums import TA_CENTER  # noqa: E402
from reportlab.lib.pagesizes import A4  # noqa: E402
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet  # noqa: E402
from reportlab.lib.units import cm  # noqa: E402
from reportlab.platypus import (Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer,  # noqa: E402
                                Table, TableStyle)

import fin  # noqa: E402
from excel_export import RATIO_XL, SCORE_XL  # noqa: E402

C = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
INK, MUTED, GRID = "#1f1f1f", "#6b6b6b", "#e4e4e4"

ss = getSampleStyleSheet()
H1 = ParagraphStyle("H1", parent=ss["Heading1"], fontSize=18, spaceAfter=8, textColor=colors.HexColor(INK))
H2 = ParagraphStyle("H2", parent=ss["Heading2"], fontSize=13.5, spaceBefore=10, spaceAfter=6,
                    textColor=colors.HexColor(C[0]))
H3 = ParagraphStyle("H3", parent=ss["Heading3"], fontSize=11, spaceBefore=8, spaceAfter=3)
BODY = ParagraphStyle("B", parent=ss["BodyText"], fontSize=9.5, leading=13)
SMALL = ParagraphStyle("S", parent=BODY, fontSize=8, leading=10, textColor=colors.HexColor(MUTED))
CELL = ParagraphStyle("Cell", parent=BODY, fontSize=8, leading=10)
FORMULA = ParagraphStyle("F", parent=BODY, fontName="Courier", fontSize=8.5, leading=11,
                         backColor=colors.HexColor("#f3f5f9"), borderPadding=5, spaceBefore=3, spaceAfter=6)
TITLE = ParagraphStyle("T", parent=H1, fontSize=26, leading=32, alignment=TA_CENTER)
SUB = ParagraphStyle("Sub", parent=BODY, fontSize=12, alignment=TA_CENTER, textColor=colors.HexColor(MUTED))


def _esc(s: str) -> str:
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _fmt(v, nd=2):
    if v is None or (isinstance(v, float) and not np.isfinite(v)) or pd.isna(v):
        return "-"
    return f"{v:,.{nd}f}"


def _table(rows, col_widths=None, header=True, zebra=True):
    rows = [[Paragraph(_esc(c) if not isinstance(c, Paragraph) else c.text, CELL) if isinstance(c, str) else c
             for c in r] for r in rows]
    t = Table(rows, colWidths=col_widths, repeatRows=1 if header else 0)
    style = [("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#d0d0d0")),
             ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
             ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]
    if header:
        style += [("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(C[0])),
                  ("TEXTCOLOR", (0, 0), (-1, 0), colors.white)]
    if zebra:
        for i in range(1 if header else 0, len(rows)):
            if i % 2 == 0:
                style.append(("BACKGROUND", (0, i), (-1, i), colors.HexColor("#f6f7f9")))
    t.setStyle(TableStyle(style))
    return t


def _header_cells(cells):
    return [Paragraph(f"<font color='white'><b>{_esc(c)}</b></font>", CELL) for c in cells]


def _footer(title):
    def draw(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(colors.HexColor(MUTED))
        canvas.drawString(1.8 * cm, 1.1 * cm, title)
        canvas.drawRightString(A4[0] - 1.8 * cm, 1.1 * cm, f"page {doc.page}")
        canvas.restoreState()
    return draw


def _doc(buf, title):
    return SimpleDocTemplate(buf, pagesize=A4, leftMargin=1.8 * cm, rightMargin=1.8 * cm,
                             topMargin=1.6 * cm, bottomMargin=1.8 * cm, title=title)


# ---------------------------------------------------------------------------
# Charts (matplotlib -> PNG)
# ---------------------------------------------------------------------------
def _ax_style(ax, title):
    ax.set_title(title, loc="left", fontsize=10, color=INK, pad=8)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.spines["left"].set_color(GRID)
    ax.spines["bottom"].set_color("#bbbbbb")
    ax.tick_params(colors=MUTED, labelsize=8)
    ax.grid(axis="y", color=GRID, linewidth=0.7)
    ax.set_axisbelow(True)


def _png(fig, width_cm=17.4):
    b = io.BytesIO()
    fig.savefig(b, format="png", dpi=170, bbox_inches="tight")
    plt.close(fig)
    b.seek(0)
    w, h = fig.get_size_inches()
    return Image(b, width=width_cm * cm, height=width_cm * cm * h / w)


def _legend_below(ax, n):
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.1), ncol=min(n, 4), frameon=False, fontsize=8)


def chart_profit(d, scale, unit):
    years = [str(y) for y in d.columns]
    x = np.arange(len(years))
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(10, 3.6))
    keys = [("revenue", "Revenue"), ("gross_profit", "Gross profit"), ("operating_profit", "Operating profit"),
            ("net_profit", "Net profit")]
    w = 0.19
    for i, (k, lab) in enumerate(keys):
        a1.bar(x + (i - 1.5) * w, d.loc[k].values / scale, w * 0.92, color=C[i], label=lab)
    a1.set_xticks(x, years)
    _ax_style(a1, f"Revenue to net profit ({unit})")
    _legend_below(a1, 4)
    bottom = np.zeros(len(years))
    for i, (k, lab) in enumerate([("cost_of_sales", "Cost of sales"), ("sga", "Distribution + G&A"),
                                  ("rd", "R&D"), ("other_opex", "Other operational")]):
        v = np.nan_to_num(d.loc[k].values.astype(float)) / scale
        a2.bar(x, v, 0.55, bottom=bottom, color=C[i], label=lab, edgecolor="white", linewidth=1)
        bottom += v
    a2.set_xticks(x, years)
    _ax_style(a2, f"Cost structure ({unit})")
    _legend_below(a2, 4)
    fig.tight_layout()
    return _png(fig)


def chart_balance(d, scale, unit):
    years = [str(y) for y in d.columns]
    x = np.arange(len(years))
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(10, 3.8), sharey=True)
    g = lambda k: np.nan_to_num(d.loc[k].values.astype(float)) / scale  # noqa: E731
    other = g("current_assets") - g("cash") - g("st_investments") - g("receivables") - g("inventory")
    parts = [("Cash", g("cash")), ("ST investments", g("st_investments")), ("Receivables", g("receivables")),
             ("Inventories", g("inventory")), ("Other current", other),
             ("Long-term assets", g("total_assets") - g("current_assets"))]
    b = np.zeros(len(years))
    for i, (lab, v) in enumerate(parts):
        a1.bar(x, v, 0.55, bottom=b, color=C[i], label=lab, edgecolor="white", linewidth=1)
        b += v
    a1.set_xticks(x, years)
    _ax_style(a1, f"Assets ({unit})")
    _legend_below(a1, 3)
    pos, neg = np.zeros(len(years)), np.zeros(len(years))
    for lab, v, col in [("ST debt", g("current_liabilities"), C[7]), ("LT debt", g("noncurrent_liabilities"), C[3]),
                        ("Equity", g("equity"), C[6])]:
        base = np.where(v >= 0, pos, neg)
        a2.bar(x, v, 0.55, bottom=base, color=col, label=lab, edgecolor="white", linewidth=1)
        pos, neg = np.where(v >= 0, pos + v, pos), np.where(v < 0, neg + v, neg)
    a2.set_xticks(x, years)
    _ax_style(a2, f"Liabilities + equity ({unit})")
    _legend_below(a2, 3)
    fig.tight_layout()
    return _png(fig)


NORMS = {"abs_liquidity": (0.2, 0.25), "quick_liquidity": (0.7, 0.8), "current_liquidity": (2, 2.5)}


def chart_small_multiples(series: dict, bands: dict, ncols=3, height=2.5):
    """series: title -> pd.Series; bands: title -> [(lo, hi, color, label)]"""
    n = len(series)
    rows = math.ceil(n / ncols)
    fig, axes = plt.subplots(rows, ncols, figsize=(10, height * rows), squeeze=False)
    for ax, (title, s) in zip(axes.flat, series.items()):
        years = [str(y) for y in s.index]
        vals = s.values.astype(float)
        finite = vals[np.isfinite(vals)]
        ext = [v for b in bands.get(title, []) for v in b[:2] if v is not None and np.isfinite(v)]
        allv = np.concatenate([finite, ext]) if len(finite) or ext else np.array([0, 1])
        lo, hi = allv.min(), allv.max()
        span = (hi - lo) or abs(hi) or 1
        ylo, yhi = lo - span * 0.15, hi + span * 0.3
        for b_lo, b_hi, col, lab in bands.get(title, []):
            ax.axhspan(max(b_lo, ylo) if b_lo is not None else ylo, min(b_hi, yhi) if b_hi is not None else yhi,
                       color=col, alpha=0.14, lw=0)
            if lab:
                ax.text(0.99, (min(b_hi, yhi) if b_hi is not None else yhi), lab, transform=ax.get_yaxis_transform(),
                        ha="right", va="top", fontsize=6.5, color=MUTED)
        ax.plot(years, vals, color=C[0], lw=2, marker="o", ms=5)
        for xx, v in zip(years, vals):
            if np.isfinite(v):
                ax.annotate(f"{v:.2f}", (xx, v), textcoords="offset points", xytext=(0, 6), ha="center",
                            fontsize=7, color=INK)
        ax.set_ylim(ylo, yhi)
        _ax_style(ax, title)
    for ax in list(axes.flat)[n:]:
        ax.axis("off")
    fig.tight_layout()
    return _png(fig)


# ---------------------------------------------------------------------------
# Automatic commentary
# ---------------------------------------------------------------------------
def _assess(key, v):
    if v is None or not np.isfinite(v):
        return "no data"
    rules = {
        "abs_liquidity": (0.2, 0.25), "quick_liquidity": (0.7, 0.8), "current_liquidity": (2, 2.5),
    }
    if key in rules:
        lo, hi = rules[key]
        return "below norm" if v < lo else "above norm" if v > hi else "within norm"
    if key == "general_solvency":
        return "insolvent (<1)" if v < 1 else "acceptable" if v < 2 else "good"
    if key == "debt_ratio":
        return "high debt" if v > 0.6 else "moderate" if v > 0.5 else "good"
    if key == "debt_to_equity":
        return "negative equity" if v < 0 else "high leverage" if v > 1.5 else "moderate" if v > 1 else "good"
    if key == "interest_coverage":
        return "risky (<1.5)" if v < 1.5 else "acceptable" if v < 3 else "good"
    if key in ("return_on_sales", "net_margin", "roa", "roe", "gross_margin"):
        return "loss" if v < 0 else "weak" if v < 5 else "good"
    return ""


def commentary(d, ratios, scores, unit, scale) -> list[str]:
    y = list(d.columns)
    first, last = y[0], y[-1]
    out = []
    r0, r1 = d.at["revenue", first], d.at["revenue", last]
    if np.isfinite(r0) and np.isfinite(r1) and r0:
        n = len(y) - 1
        cagr = ((r1 / r0) ** (1 / n) - 1) * 100 if n and r0 > 0 and r1 > 0 else float("nan")
        out.append(f"Revenue went from {_fmt(r0 / scale, 1)} to {_fmt(r1 / scale, 1)} {unit} between {first} and {last} "
                   f"({(r1 / r0 - 1) * 100:+.1f}% total, {cagr:+.1f}% per year on average).")
    np1 = d.at["net_profit", last]
    if np.isfinite(np1):
        out.append(f"Net profit in {last} was {_fmt(np1 / scale, 1)} {unit}; net margin {_fmt(ratios.at['net_margin', last], 1)}%, "
                   f"return on sales (pre-tax) {_fmt(ratios.at['return_on_sales', last], 1)}% "
                   f"({'up' if ratios.at['return_on_sales', last] > ratios.at['return_on_sales', first] else 'down'} "
                   f"from {_fmt(ratios.at['return_on_sales', first], 1)}% in {first}).")
    cl = ratios.at["current_liquidity", last]
    if np.isfinite(cl):
        out.append(f"Current liquidity {cl:.2f} is {_assess('current_liquidity', cl)} (2-2.5): current assets cover "
                   f"short-term debts {cl:.2f} times. Quick liquidity {_fmt(ratios.at['quick_liquidity', last])} "
                   f"({_assess('quick_liquidity', ratios.at['quick_liquidity', last])}, 0.7-0.8), absolute liquidity "
                   f"{_fmt(ratios.at['abs_liquidity', last])} ({_assess('abs_liquidity', ratios.at['abs_liquidity', last])}, 0.2-0.25).")
    dr = ratios.at["debt_ratio", last]
    if np.isfinite(dr):
        out.append(f"Debts finance {dr * 100:.0f}% of assets (debt ratio {dr:.2f}, {_assess('debt_ratio', dr)}); general solvency "
                   f"{_fmt(ratios.at['general_solvency', last])} - assets cover all debts that many times.")
    zs = []
    for k in fin.SCORE_INFO:
        z = scores.at[k, last]
        if np.isfinite(z):
            zs.append(f"{fin.SCORE_INFO[k]['label']}: {z:.2f} ({fin.interpret(k, z)})")
    if zs:
        out.append(f"Bankruptcy-risk models for {last} - " + "; ".join(zs) + ".")
    if cl is not None and np.isfinite(cl) and cl < 1 and np.isfinite(np1) and np1 > 0:
        out.append("Note: low liquidity together with high profitability usually signals deliberate working-capital "
                   "management (large companies pay suppliers late and keep cash low), not distress. Read ratios "
                   "together, never one alone.")
    return out


# ---------------------------------------------------------------------------
# Company report
# ---------------------------------------------------------------------------
def build_report(d, info, ratios, scores, parts, scale, unit) -> bytes:
    name = info.get("name", "Company")
    years = list(d.columns)
    buf = io.BytesIO()
    doc = _doc(buf, f"{name} - financial analysis")
    s = []

    s += [Spacer(1, 5 * cm), Paragraph(_esc(name), TITLE), Spacer(1, 0.3 * cm),
          Paragraph("Financial analysis report", SUB), Spacer(1, 0.3 * cm),
          Paragraph(_esc(" | ".join(x for x in [info.get("symbol"), info.get("sector"), info.get("industry"),
                                                info.get("country")] if x)), SUB),
          Spacer(1, 0.3 * cm),
          Paragraph(f"Period {years[0]}-{years[-1]} | figures in {_esc(unit)} | generated {date.today():%d %b %Y}", SUB),
          Spacer(1, 0.3 * cm),
          Paragraph("Source: " + ("Yahoo Finance annual statements" if info.get("symbol") else "manual input"), SUB),
          PageBreak()]

    s.append(Paragraph("1. Summary", H1))
    for line in commentary(d, ratios, scores, unit, scale):
        s.append(Paragraph("&bull; " + _esc(line), BODY))
        s.append(Spacer(1, 3))
    last = years[-1]
    kp = [["Indicator", f"{last}", "Assessment"]]
    for k in ["return_on_sales", "roa", "roe", "current_liquidity", "quick_liquidity", "abs_liquidity",
              "general_solvency", "debt_ratio"]:
        kp.append([fin.RATIOS[k][0] + f" ({fin.RATIOS[k][5]})", _fmt(ratios.at[k, last]), _assess(k, ratios.at[k, last])])
    s += [Spacer(1, 6), _table([_header_cells(kp[0])] + kp[1:], [9 * cm, 3 * cm, 5.4 * cm])]

    s += [PageBreak(), Paragraph("2. Financial statements", H1)]
    for stmt in ["Balance sheet", "Income statement", "Cash flow"]:
        keys = [k for k, v in fin.INPUTS.items() if v[1] == stmt]
        rows = [_header_cells([f"{stmt} ({unit})"] + [str(y) for y in years])]
        for k in keys:
            rows.append([fin.INPUTS[k][0]] + [_fmt(d.at[k, y] / scale, 1) for y in years])
        w = (17.4 - 7) / len(years)
        s += [Paragraph(stmt, H2), _table(rows, [7 * cm] + [w * cm] * len(years))]

    s += [PageBreak(), Paragraph("3. Profitability and costs", H1), chart_profit(d, scale, unit), Spacer(1, 6),
          chart_small_multiples({fin.RATIOS[k][0] + " %": ratios.loc[k] for k in
                                 ["return_on_sales", "roa", "roe", "gross_margin", "net_margin"]}, {})]
    s += [PageBreak(), Paragraph("4. Balance sheet structure", H1), chart_balance(d, scale, unit)]
    v = fin.vertical_analysis(d)
    rows = [_header_cells(["% of total assets"] + [str(y) for y in years])]
    rows += [[fin.INPUTS[k][0]] + [_fmt(v.at[k, y], 1) + "%" for y in years] for k in v.index]
    w = (17.4 - 7) / len(years)
    s += [Spacer(1, 6), _table(rows, [7 * cm] + [w * cm] * len(years))]

    s += [PageBreak(), Paragraph("5. Ratios", H1)]
    green = C[2]
    s.append(chart_small_multiples(
        {fin.RATIOS[k][0]: ratios.loc[k] for k in ["abs_liquidity", "quick_liquidity", "current_liquidity",
                                                   "general_solvency", "debt_ratio", "receivables_turnover"]},
        {fin.RATIOS["abs_liquidity"][0]: [(0.2, 0.25, green, "norm")],
         fin.RATIOS["quick_liquidity"][0]: [(0.7, 0.8, green, "norm")],
         fin.RATIOS["current_liquidity"][0]: [(2, 2.5, green, "norm")],
         fin.RATIOS["general_solvency"][0]: [(2, None, green, "good > 2")],
         fin.RATIOS["debt_ratio"][0]: [(None, 0.5, green, "good < 0.5")]}))
    groups = {}
    for k, v in fin.RATIOS.items():
        groups.setdefault(v[1], []).append(k)
    for grp, keys in groups.items():
        rows = [_header_cells(["Ratio", "Norm"] + [str(y) for y in years] + ["Assessment " + str(last)])]
        for k in keys:
            rows.append([f"{fin.RATIOS[k][0]} ({fin.RATIOS[k][5]})", fin.RATIOS[k][3]]
                        + [_fmt(ratios.at[k, y]) for y in years] + [_assess(k, ratios.at[k, last])])
        w = (17.4 - 5.2 - 3.4 - 2.6) / len(years)
        s += [KeepTogether([Paragraph(grp, H2), _table(rows, [5.2 * cm, 3.4 * cm] + [w * cm] * len(years) + [2.6 * cm])])]

    s += [PageBreak(), Paragraph("6. Bankruptcy-risk models", H1)]
    zone_cols = [C[7], C[3], C[2]]
    s.append(chart_small_multiples(
        {fin.SCORE_INFO[k]["label"]: scores.loc[k] for k in fin.SCORE_INFO},
        {fin.SCORE_INFO[k]["label"]: [(None if not np.isfinite(lo) else lo, None if not np.isfinite(hi) else hi, col, lab)
                                      for (lo, hi, lab), col in zip(fin.SCORE_INFO[k]["zones"], zone_cols)]
         for k in fin.SCORE_INFO}, ncols=2, height=2.8))
    for k, si in fin.SCORE_INFO.items():
        rows = [_header_cells([si["label"]] + [str(y) for y in years])]
        for xk, sv in parts[k].items():
            rows.append([xk] + [_fmt(sv[y], 3) for y in years])
        rows.append(["Z"] + [_fmt(scores.at[k, y], 3) for y in years])
        rows.append(["Interpretation"] + [fin.interpret(k, scores.at[k, y]) for y in years])
        w = (17.4 - 4) / len(years)
        s += [KeepTogether([Spacer(1, 6), _table(rows, [4 * cm] + [w * cm] * len(years)),
                            Paragraph(_esc(si["formula"]).replace("\n", "<br/>"), SMALL)])]
    if d.loc["personnel_costs"].isna().all():
        s.append(Paragraph("Personnel costs not available: Conan-Holder X5 set to 0 (score slightly optimistic).", SMALL))

    s += [PageBreak(), Paragraph("Appendix - formulas used", H1)]
    for k, (label, grp, formula, norm, meaning, unit_) in fin.RATIOS.items():
        s.append(Paragraph(f"<b>{_esc(label)}</b> = {_esc(formula)}. Norm: {_esc(norm)}. {_esc(meaning)}", BODY))
        s.append(Spacer(1, 2))

    doc.build(s, onFirstPage=lambda c, d_: None, onLaterPages=_footer(f"{name} - financial analysis"))
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Study guide
# ---------------------------------------------------------------------------
RATIO_LEARN = {
    "return_on_sales": ("High = company keeps a big part of each sale as profit (pricing power, low costs). "
                        "Low/negative = costs eat the sales.", "Low: raise prices, cut costs, change product mix."),
    "roa": ("Shows how well management uses everything the company owns. Asset-heavy industries "
            "(energy, telecom) have low ROA; software/brands have high ROA.", "Average assets are used because profit "
                                                                              "is earned during the whole year."),
    "roe": ("What shareholders earn on their capital. Very high ROE may come from very low equity "
            "(lots of debt or share buybacks), not only from high profit.", "Compare with cost of equity (CAPM)."),
    "gross_margin": ("Measures production efficiency and pricing power before overheads.", ""),
    "net_margin": ("Final profit per 100 of sales after all costs, interest and tax.", ""),
    "abs_liquidity": ("Too low = cannot pay suppliers today without new cash. Too high = idle cash that earns nothing.",
                      "Only cash in numerator - strictest liquidity test."),
    "quick_liquidity": ("Excludes inventories because they are the slowest to turn into cash.",
                        "Also called acid-test ratio."),
    "current_liquidity": ("< 1 = short-term debts exceed current assets (risk, or very efficient working capital). "
                          "> 3 = maybe too much money stuck in stock/receivables.", "Also called current ratio."),
    "general_solvency": ("< 1 = debts larger than all assets: company technically insolvent.",
                         "Inverse of the total debt ratio."),
    "debt_ratio": ("High = financed mostly by creditors: higher financial risk, interest burden.",
                   "Equity ratio = 1 - debt ratio (if all liabilities counted)."),
    "debt_to_equity": ("Leverage. Debt raises ROE when business earns more than interest rate, but raises risk.",
                       "Negative if equity is negative."),
    "interest_coverage": ("< 1.5 = profit barely pays the interest; banks get worried.", ""),
    "receivables_turnover": ("High = customers pay quickly. Falling turnover = collection problems.", ""),
    "receivables_days": ("Compare with payment terms given to customers (e.g. 30 days).", ""),
    "dts_turnover": ("How many times a year sales could repay short-term debts.", ""),
    "asset_turnover": ("Efficiency: sales per 1 of assets. ROA = net margin x asset turnover (DuPont).", ""),
}

GLOSSARY_EXTRA = [
    ("Assets", "Resources the company controls and expects to bring future benefits (buildings, machines, stock, cash)."),
    ("Liabilities (debts)", "Obligations to pay others: suppliers, banks, state, employees."),
    ("Equity (own capital)", "Owners' claim on assets = Assets - Liabilities. Share capital + reserves + retained profit."),
    ("Accounting equation", "Assets = Liabilities + Equity. Always true - the balance sheet 'balances'."),
    ("Working capital", "Current assets - Current liabilities. Money available to run day-to-day operations."),
    ("Permanent capital", "Equity + Long-term debt. Stable money that should finance long-term assets."),
    ("Liquidity", "Ability to pay short-term debts on time."),
    ("Solvency", "Ability to pay ALL debts (short + long term) with all assets; long-term survival."),
    ("Profitability (rentabilitate)", "Ability to generate profit relative to sales, assets or equity."),
    ("EBIT", "Earnings Before Interest and Taxes = operating profit."),
    ("EBITDA", "EBIT + depreciation & amortisation. Cash-like operating profit."),
    ("Depreciation", "Spreading the cost of a long-term asset over its useful life. A cost, but no cash leaves."),
    ("Retained earnings", "Profits kept in the company (not paid as dividends), accumulated over years."),
    ("Dividend", "Part of net profit paid to shareholders."),
    ("Horizontal analysis", "Compare the same line across years: (This year - Last year) / Last year x 100."),
    ("Vertical analysis", "Each line as % of a base (total assets or revenue) in the same year: structure."),
    ("Fixed costs", "Do not change with output (rent, salaries of management)."),
    ("Variable costs", "Change with output (raw materials, piece-rate labour). Zero when output is zero."),
    ("Contribution per unit", "Price - Variable cost per unit. Covers fixed costs, then becomes profit."),
    ("Break-even point", "Output where total revenue = total costs: Fixed costs / contribution per unit."),
    ("Margin of safety", "Actual output - break-even output."),
    ("EPS", "Earnings per share = Net profit / Number of shares."),
    ("P/E ratio", "Share price / EPS. How much investors pay for 1 of yearly earnings."),
    ("Beta", "Sensitivity of a share to market moves. 1 = like market, >1 = more volatile."),
    ("Coupon", "Annual interest a bond pays = coupon rate x face (par) value."),
    ("Yield to maturity (YTM)", "Total annual return if a bond is held to maturity; the discount rate that makes "
                                "PV of cash flows = price."),
]


def _substitute(tpl: str, d: pd.DataFrame, year, scale: float) -> str:
    years = list(d.columns)

    def sub(m):
        key, prev = m.group(1), m.group(2)
        y = years[max(0, years.index(year) - 1)] if prev else year
        v = d.at[key, y]
        return _fmt((0 if pd.isna(v) else v) / scale, 1)
    expr = re.sub(r"\{(\w+)(@prev)?\}", sub, tpl.lstrip("="))
    return expr.replace("IFERROR(", "(").replace(",0)", ")")


def _bond_price(face, coupon_rate, ytm, n):
    c = face * coupon_rate
    return sum(c / (1 + ytm) ** t for t in range(1, n + 1)) + face / (1 + ytm) ** n


def course_examples() -> list[tuple[str, str, str]]:
    """(question, formula, worked solution) computed here so numbers are exact."""
    ex = []
    ex.append(("Bond face 1000 sells at 1200, coupon 12%, 10 years. Current yield?",
               "Current yield = Annual coupon / Price",
               f"Coupon = 12% x 1000 = 120. CY = 120 / 1200 = {120 / 1200 * 100:.2f}%"))
    for q, f, c, y, n in [("3-year bond, par 1000, coupon 5%, yield 6%. Price?", 1000, .05, .06, 3),
                          ("1000 bond, 8% coupon, 15 years, market rate 10%. Value?", 1000, .08, .10, 15),
                          ("Coupon 10% annual, par 1000, 5 years, YTM 11%. Value?", 1000, .10, .11, 5),
                          ("10% annual coupon, face 1000, 20 years, YTM 8%. Price?", 1000, .10, .08, 20)]:
        p = _bond_price(f, c, y, n)
        ex.append((q, "P = C x [1 - (1+r)^-n] / r + F / (1+r)^n",
                   f"C = {f * c:.0f}, r = {y:.0%}, n = {n}: P = {f * c:.0f} x {(1 - (1 + y) ** -n) / y:.4f} + "
                   f"{f} / {(1 + y) ** n:.4f} = {p:,.2f}  ({'discount' if p < f else 'premium'}: coupon "
                   f"{'<' if c < y else '>'} market rate)"))
    ex.append(("10% coupon, 15 years, par 1000, price 928.09. Yield more or less than 10%?",
               "Price < par  <=>  YTM > coupon rate",
               "Price 928.09 < 1000, so the bond sells at a discount: YTM is MORE than 10% (about 11%)."))
    p = _bond_price(1000, .04, .045, 30)
    ex.append(("1000 bond, 8% coupon paid semiannually, 15 years, YTM 9%. Price?",
               "Semiannual: C/2, r/2, 2n periods",
               f"C/2 = 40, r = 4.5%, n = 30: P = {_bond_price(1000, .04, .045, 30):,.2f}  -> answer b) 919"))
    ex.append(("Account pays 8%/year; balance at 21st birthday 5033.83. Initial deposit?",
               "PV = FV / (1 + r)^n", f"PV = 5033.83 / 1.08^21 = 5033.83 / {1.08 ** 21:.4f} = {5033.83 / 1.08 ** 21:,.2f}"))
    ex.append(("Future value of 5000 in 5 years at 7%?", "FV = PV x (1 + r)^n",
               f"FV = 5000 x 1.07^5 = 5000 x {1.07 ** 5:.4f} = {5000 * 1.07 ** 5:,.2f}"))
    ex.append(("Beta 1.24, risk-free 4.2%, market risk premium 8%. Cost of equity?",
               "CAPM: Re = Rf + Beta x (Rm - Rf)", f"Re = 4.2% + 1.24 x 8% = {4.2 + 1.24 * 8:.2f}%"))
    ex.append(("9% preferred stock, par 100, price 64. Cost of preferred?", "Rp = D / P0",
               f"D = 9% x 100 = 9; Rp = 9 / 64 = {9 / 64 * 100:.2f}%"))
    ex.append(("ROE 12%, payout 40%. Sustainable growth?", "g = ROE x retention ratio (b = 1 - payout)",
               f"g = 12% x 60% = {12 * .6:.1f}%"))
    ex.append(("Dividend next year 4, required return 10%, growth 7%. Share price?", "Gordon: P0 = D1 / (r - g)",
               f"P0 = 4 / (0.10 - 0.07) = {4 / .03:,.2f}"))
    ex.append(("Widget variable cost 500, fixed costs 100,000, expected sales 1,000 units. Break-even price?",
               "Fixed costs = (Price - Variable cost) x Quantity", "100,000 = (P - 500) x 1,000  ->  P = 600"))
    ex.append(("Tiles sell at 1, fixed costs 100,000, 10 million tiles/year. Max purchase cost per tile?",
               "Fixed costs = (Price - Variable cost) x Quantity", "100,000 = (1 - VC) x 10,000,000  ->  VC = 0.99"))
    ex.append(("Current assets 150,000, current liabilities 100,000. Current ratio?",
               "Current ratio = Current assets / Current liabilities", "150,000 / 100,000 = 1.5 (below 2-2.5 norm)"))
    return ex


QUIZ = [
    ("Cash is a: long-term asset / current asset / current liability?", "Current asset."),
    ("Which statement shows the financial position at a single date?", "Balance sheet."),
    ("Formula of the current ratio?", "Current assets / Current liabilities."),
    ("Why does quick liquidity exclude inventories?", "Inventories are the slowest current asset to turn into cash."),
    ("General solvency = 0.9. What does it mean?", "Debts exceed total assets - the company is insolvent."),
    ("Debt ratio 0.7 - what share of assets is financed by owners?", "About 30% (1 - 0.7)."),
    ("Why is ROA computed with AVERAGE total assets?", "Profit is earned during the whole year, while assets change."),
    ("Return on sales falls while revenue grows. Likely cause?", "Costs grew faster than sales (margin squeeze)."),
    ("Altman Z = 2.4 (course thresholds 1.8 / 3). Interpretation?", "Grey (difficult) zone - uncertain."),
    ("Which ratio uses (Gross profit / Sales) x 100?", "Gross profit percentage."),
    ("P/E ratio formula?", "Share price / EPS."),
    ("Operating cash flow increases when depreciation increases. Why?",
     "Depreciation reduces taxable profit (tax saving) but no cash leaves the company."),
    ("Variable costs when output is zero?", "Zero."),
    ("Break-even point formula in units?", "Fixed costs / (Price - Variable cost per unit) = Fixed costs / contribution."),
    ("Bond price is above par. Is YTM above or below the coupon rate?", "Below the coupon rate."),
    ("Working capital decision example?", "How much cash the company keeps in reserve."),
    ("Receivables turnover 12. Average collection period?", "365 / 12 = about 30 days."),
    ("ROE very high but equity very small - good or bad?", "Be careful: high ROE may come from high debt/low equity, i.e. high risk."),
]


def build_study_guide(d, info, ratios, scores, scale, unit) -> bytes:
    name = info.get("name", "Company")
    years = list(d.columns)
    last = years[-1]
    buf = io.BytesIO()
    doc = _doc(buf, "Financial analysis - study guide")
    s = [Spacer(1, 5 * cm), Paragraph("Financial Analysis", TITLE), Paragraph("Study guide", SUB), Spacer(1, 0.3 * cm),
         Paragraph(f"Terms, formulas, meaning, worked examples on {_esc(name)} ({last}) and self-test", SUB),
         Spacer(1, 0.3 * cm), Paragraph(f"Company figures in {_esc(unit)}", SUB), PageBreak()]

    s += [Paragraph("1. The three financial statements", H1),
          Paragraph("<b>Balance sheet</b> - a photo of the company at one date (usually 31 December). "
                    "Left: <b>assets</b> (what it owns). Right: <b>liabilities + equity</b> (who paid for those assets). "
                    "Assets = Liabilities + Equity, always.", BODY), Spacer(1, 4),
          Paragraph("<b>Income statement</b> (profit and loss) - a film of the whole year: revenues minus costs = profit.",
                    BODY), Spacer(1, 4),
          Paragraph("Revenue - Cost of sales = Gross profit<br/>"
                    "Gross profit - Distribution, G&amp;A, other operating costs = Operating profit (EBIT)<br/>"
                    "Operating profit +/- Financial result = Profit before tax<br/>"
                    "Profit before tax - Income tax = Net profit -&gt; Dividends + Retained profit", FORMULA),
          Paragraph("<b>Cash flow statement</b> - real money in and out (operating, investing, financing). "
                    "A profitable company can still run out of cash.", BODY), Spacer(1, 4),
          Paragraph("<b>Short term (ST, current)</b> = within 1 year. <b>Long term (LT, non-current)</b> = after 1 year.", BODY)]

    s += [Paragraph("2. Glossary - statement lines", H2)]
    rows = [_header_cells(["Term", "Statement", "Meaning", f"{name[:18]} {last}"])]
    for k, (label, stmt, meaning) in fin.INPUTS.items():
        rows.append([label, stmt, meaning, _fmt(d.at[k, last] / scale, 1)])
    s.append(_table(rows, [3.8 * cm, 2.4 * cm, 8.6 * cm, 2.6 * cm]))
    s += [Paragraph("3. Glossary - key concepts", H2)]
    rows = [_header_cells(["Term", "Meaning"])] + [[t, m] for t, m in GLOSSARY_EXTRA]
    s.append(_table(rows, [4.5 * cm, 12.9 * cm]))

    s += [PageBreak(), Paragraph("4. Ratios - formula, meaning, worked example", H1),
          Paragraph(f"Each example uses real {_esc(name)} data for {last} ({_esc(unit)}). Substitute the numbers "
                    "yourself and check you get the same result.", BODY)]
    for k, (label, grp, formula, norm, meaning, u) in fin.RATIOS.items():
        interp, tip = RATIO_LEARN.get(k, ("", ""))
        example = _substitute(RATIO_XL[k], d, last, scale) if k in RATIO_XL else ""
        if k == "receivables_days":
            example = f"365 / {_fmt(ratios.at['receivables_turnover', last])}"
        block = [Paragraph(f"{_esc(label)} <font color='{MUTED}' size='8'>({grp})</font>", H3),
                 Paragraph(f"{_esc(label)} = {_esc(formula)}", FORMULA),
                 Paragraph(f"<b>Meaning:</b> {_esc(meaning)}", BODY),
                 Paragraph(f"<b>Norm:</b> {_esc(norm)}. <b>How to read:</b> {_esc(interp)} {_esc(tip)}", BODY)]
        val = ratios.at[k, last]
        if example and np.isfinite(val):
            verdict = _assess(k, val)
            block.append(Paragraph(f"<b>Example ({last}):</b> {_esc(example)} = <b>{_fmt(val)} {u}</b>"
                                   + (f" -&gt; {_esc(verdict)}" if verdict else ""), BODY))
        elif example:
            block.append(Paragraph(f"<b>Example ({last}):</b> not available - input missing for this company.", BODY))
        s.append(KeepTogether(block))

    s += [PageBreak(), Paragraph("5. Bankruptcy-risk models", H1),
          Paragraph("Combine several ratios into one score (Z) with weights found statistically on companies that did and "
                    "did not go bankrupt. Compare Z with the thresholds (zones).", BODY)]
    for k, si in fin.SCORE_INFO.items():
        zones = "; ".join(f"{lab}" + (f" if Z &lt; {hi}" if np.isfinite(hi) else " otherwise") for _, hi, lab in si["zones"])
        s.append(KeepTogether([
            Paragraph(_esc(si["label"]), H3),
            Paragraph(_esc(si["formula"]).replace("\n", "<br/>"), FORMULA),
            Paragraph(f"<b>Zones:</b> {zones}", BODY),
            Paragraph(f"<b>Example ({last}):</b> Z = {_esc(_substitute(SCORE_XL[k], d, last, scale))}"
                      f" = <b>{_fmt(scores.at[k, last], 3)}</b> -&gt; {_esc(fin.interpret(k, scores.at[k, last]))}",
                      SMALL)]))

    s += [PageBreak(), Paragraph("6. Course formulas with solved exercises", H1)]
    for i, (q, f, sol) in enumerate(course_examples(), 1):
        s.append(KeepTogether([Paragraph(f"<b>{i}. {_esc(q)}</b>", BODY), Paragraph(_esc(f), FORMULA),
                               Paragraph(_esc(sol), BODY), Spacer(1, 5)]))

    s += [PageBreak(), Paragraph("7. Self-test", H1),
          Paragraph("Cover the answers, try each question, then check.", BODY), Spacer(1, 4)]
    for i, (q, _) in enumerate(QUIZ, 1):
        s.append(Paragraph(f"{i}. {_esc(q)}", BODY))
        s.append(Spacer(1, 3))
    s += [Spacer(1, 10), Paragraph("Answers", H2)]
    for i, (_, a) in enumerate(QUIZ, 1):
        s.append(Paragraph(f"{i}. {_esc(a)}", SMALL))

    doc.build(s, onFirstPage=lambda c, d_: None, onLaterPages=_footer("Financial analysis - study guide"))
    return buf.getvalue()


def flashcards_csv() -> str:
    """Front;Back - imports into Anki / Quizlet."""
    rows = [(f"{lab} - meaning?", meaning) for lab, _, meaning in fin.INPUTS.values()]
    rows += [(t, m) for t, m in GLOSSARY_EXTRA]
    rows += [(f"{v[0]} - formula?", f"{v[2]} | norm: {v[3]}") for v in fin.RATIOS.values()]
    rows += [(f"{v[0]} - what does it show?", v[4]) for v in fin.RATIOS.values()]
    rows += [(si["label"] + " - formula?", si["formula"].replace("\n", " | ")) for si in fin.SCORE_INFO.values()]
    rows += [(f"{q[0]}", f"{q[1]} | {q[2]}") for q in course_examples()]
    rows += QUIZ
    return "\n".join(f'"{a.replace(chr(34), chr(39))}";"{b.replace(chr(34), chr(39))}"' for a, b in rows)
