"""Financial data + ratio engine.

Inputs mirror the course Excel templates (Financial indicators(2025).xlsx and
Solvency.xlsx). Data comes from Yahoo Finance (yfinance) or from manual entry.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import yfinance as yf

# ---------------------------------------------------------------------------
# Inputs: key -> (label, statement, explanation)
# ---------------------------------------------------------------------------
INPUTS = {
    # Balance sheet - assets
    "cash": ("Cash", "Balance sheet", "Cash and cash equivalents: money in bank + very liquid deposits (< 3 months)."),
    "st_investments": ("Investments on ST", "Balance sheet", "Short-term investments (securities, deposits) that can be sold within a year."),
    "receivables": ("Account receivables on ST", "Balance sheet", "Money customers owe the company for goods already delivered."),
    "inventory": ("Inventories", "Balance sheet", "Raw materials, work in progress and finished goods not yet sold."),
    "current_assets": ("Current assets", "Balance sheet", "Assets that turn into cash within one year: cash + ST investments + receivables + inventories + other."),
    "total_assets": ("Total assets", "Balance sheet", "Everything the company owns = current assets + long-term (fixed) assets."),
    # Balance sheet - liabilities & equity
    "current_liabilities": ("Debt on ST", "Balance sheet", "Short-term liabilities (due within 1 year): suppliers, short loans, taxes, salaries payable."),
    "noncurrent_liabilities": ("Debt on LT", "Balance sheet", "Long-term liabilities (due after 1 year): bank loans, bonds, leases."),
    "total_liabilities": ("Total liabilities (debts)", "Balance sheet", "All debts = ST debt + LT debt."),
    "equity": ("Own capital / Equity", "Balance sheet", "Owners' money = total assets - total liabilities (share capital + retained earnings + reserves)."),
    "retained_earnings": ("Retained (unreparted) profit", "Balance sheet", "Accumulated profits from all years not paid out as dividends."),
    # Income statement
    "revenue": ("Revenue from sales", "Income statement", "Sales of goods/services in the year (top line)."),
    "cost_of_sales": ("Cost of sales", "Income statement", "Direct costs of what was sold (materials, production labour)."),
    "gross_profit": ("Gross profit", "Income statement", "Revenue - cost of sales."),
    "sga": ("Distribution + general & administrative expenses", "Income statement", "Selling, marketing, office, management costs (SG&A)."),
    "rd": ("Research & development", "Income statement", "R&D costs (Yahoo reports it separately; course template puts it in other operating expenses)."),
    "other_opex": ("Other operational expenses", "Income statement", "Any remaining operating costs."),
    "operating_profit": ("Operating profit", "Income statement", "Gross profit - operating expenses. Profit from the core business."),
    "ebitda": ("EBITDA", "Income statement", "Operating profit before depreciation & amortisation; proxy for gross operating surplus."),
    "financial_expenses": ("Financial expenses (interest)", "Income statement", "Interest paid on loans and bonds."),
    "personnel_costs": ("Costs of personnel", "Income statement", "Salaries + social contributions. Often not published by US companies."),
    "pretax_profit": ("Profit before tax", "Income statement", "Operating profit +/- financial result. Profit before income tax."),
    "net_profit": ("Net profit", "Income statement", "Profit before tax - income tax. The bottom line."),
    "dividends": ("Dividends paid", "Cash flow", "Cash paid to shareholders in the year."),
}

# Template rows used in manual entry (others derived if blank)
MANUAL_KEYS = list(INPUTS)

YAHOO_MAP = {
    "cash": ["Cash And Cash Equivalents", "Cash Financial"],
    "st_investments": ["Other Short Term Investments", "Short Term Investments"],
    "receivables": ["Accounts Receivable", "Receivables"],
    "inventory": ["Inventory"],
    "current_assets": ["Current Assets"],
    "total_assets": ["Total Assets"],
    "current_liabilities": ["Current Liabilities"],
    "noncurrent_liabilities": ["Total Non Current Liabilities Net Minority Interest"],
    "total_liabilities": ["Total Liabilities Net Minority Interest"],
    "equity": ["Stockholders Equity", "Common Stock Equity"],
    "retained_earnings": ["Retained Earnings"],
    "revenue": ["Total Revenue", "Operating Revenue"],
    "cost_of_sales": ["Cost Of Revenue", "Reconciled Cost Of Revenue"],
    "gross_profit": ["Gross Profit"],
    "sga": ["Selling General And Administration"],
    "rd": ["Research And Development"],
    "operating_profit": ["Operating Income", "Total Operating Income As Reported"],
    "ebitda": ["EBITDA", "Normalized EBITDA"],
    "financial_expenses": ["Interest Expense", "Interest Expense Non Operating"],
    "personnel_costs": ["Salaries And Wages"],
    "pretax_profit": ["Pretax Income"],
    "net_profit": ["Net Income", "Net Income Common Stockholders"],
}


def search_company(query: str, n: int = 8) -> list[dict]:
    """Company name -> list of {symbol, name, exchange}."""
    quotes = yf.Search(query, max_results=n).quotes
    return [
        {"symbol": q["symbol"], "name": q.get("longname") or q.get("shortname") or q["symbol"],
         "exchange": q.get("exchDisp", ""), "type": q.get("quoteType", "")}
        for q in quotes if q.get("quoteType") in ("EQUITY", None)
    ]


def _pick(df: pd.DataFrame, names: list[str]) -> pd.Series:
    for n in names:
        if n in df.index:
            return df.loc[n]
    return pd.Series(np.nan, index=df.columns)


def from_yahoo(symbol: str) -> tuple[pd.DataFrame, dict]:
    """Return (inputs DataFrame [key x year], info dict). Values in currency units."""
    t = yf.Ticker(symbol)
    bs, inc, cf = t.balance_sheet, t.income_stmt, t.cashflow
    if bs.empty or inc.empty:
        raise ValueError(f"Yahoo has no annual statements for {symbol}")
    cols = sorted(set(bs.columns) & set(inc.columns))
    bs, inc = bs[cols], inc[cols]
    both = pd.concat([bs, inc])
    both = both[~both.index.duplicated()]
    data = {k: _pick(both, v) for k, v in YAHOO_MAP.items()}
    df = pd.DataFrame(data).T.astype(float)

    opex = _pick(inc, ["Operating Expense"]).astype(float)
    df.loc["other_opex"] = (opex - df.loc["sga"].fillna(0) - df.loc["rd"].fillna(0)).clip(lower=0)
    if not cf.empty:
        div = _pick(cf, ["Cash Dividends Paid", "Common Stock Dividend Paid"]).reindex(cols)
        df.loc["dividends"] = div.astype(float).abs()
    else:
        df.loc["dividends"] = np.nan
    df.loc["financial_expenses"] = df.loc["financial_expenses"].abs()

    df.columns = [c.year for c in cols]
    df = df.reindex(list(INPUTS))
    df = df.loc[:, ~df.columns.duplicated(keep="last")]
    df = df.dropna(axis=1, how="all")

    info = {}
    try:
        raw = t.info
        info = {
            "name": raw.get("longName") or raw.get("shortName") or symbol,
            "currency": raw.get("financialCurrency") or raw.get("currency", ""),
            "sector": raw.get("sector", ""), "industry": raw.get("industry", ""),
            "country": raw.get("country", ""), "summary": raw.get("longBusinessSummary", ""),
            "price": raw.get("currentPrice") or raw.get("regularMarketPrice"),
            "market_cap": raw.get("marketCap"), "eps": raw.get("trailingEps"),
            "pe": raw.get("trailingPE"), "beta": raw.get("beta"),
            "shares": raw.get("sharesOutstanding"),
        }
    except Exception:
        info = {"name": symbol}
    return df, info


def fill_derived(df: pd.DataFrame) -> pd.DataFrame:
    """Fill blanks that can be derived from other lines (useful for manual entry)."""
    d = df.copy()

    def fill(key, value):
        d.loc[key] = d.loc[key].where(d.loc[key].notna() & (d.loc[key] != 0), value)

    fill("total_liabilities", d.loc["current_liabilities"] + d.loc["noncurrent_liabilities"])
    fill("equity", d.loc["total_assets"] - d.loc["total_liabilities"])
    fill("gross_profit", d.loc["revenue"] - d.loc["cost_of_sales"])
    opex = d.loc[["sga", "rd", "other_opex"]].fillna(0).sum()
    fill("operating_profit", d.loc["gross_profit"] - opex)
    return d


# ---------------------------------------------------------------------------
# Ratios
# ---------------------------------------------------------------------------
def _div(a, b):
    a, b = pd.Series(a, dtype=float), pd.Series(b, dtype=float)
    return a / b.replace(0, np.nan)


RATIOS = {
    # key: (label, group, formula, norm/target, meaning, unit)
    "return_on_sales": ("Return on sales (ROS)", "Profitability", "Profit before tax / Revenue x 100",
                        "higher is better; compare with industry",
                        "How many lei/$ of profit each 100 of sales brings.", "%"),
    "roa": ("Return on assets (ROA)", "Profitability", "Profit before tax / average total assets x 100",
            "> 5% is decent for most industries",
            "How efficiently the assets generate profit. Average = (assets start of year + end of year) / 2.", "%"),
    "roe": ("Return on equity (ROE)", "Profitability", "Net profit / Equity x 100",
            "> 10-15% is good",
            "Return the owners get on their money.", "%"),
    "gross_margin": ("Gross profit percentage", "Profitability", "Gross profit / Revenue x 100",
                     "industry-specific", "Share of sales left after direct production costs.", "%"),
    "net_margin": ("Net profit margin", "Profitability", "Net profit / Revenue x 100",
                   "industry-specific", "Share of sales that ends up as final profit.", "%"),
    "abs_liquidity": ("Absolute liquidity", "Liquidity", "Cash / ST debt", "0.2 - 0.25",
                      "Share of short-term debts that can be paid immediately with cash.", "x"),
    "quick_liquidity": ("Intermediary (quick) liquidity", "Liquidity",
                        "(Cash + ST investments + ST receivables) / ST debt", "0.7 - 0.8",
                        "Ability to pay ST debts without selling inventory.", "x"),
    "current_liquidity": ("Current liquidity (current ratio)", "Liquidity", "Current assets / ST debt", "2 - 2.5",
                          "Current assets cover short-term debts this many times.", "x"),
    "general_solvency": ("General solvency", "Solvency", "Total assets / (ST debt + LT debt)", "> 1 (ideally > 2)",
                         "How many times assets cover all debts. < 1 = insolvent (debts exceed assets).", "x"),
    "debt_ratio": ("Total debt ratio", "Solvency", "(ST debt + LT debt) / Total assets", "< 0.5 - 0.6",
                   "Share of assets financed by creditors. 1 - debt ratio = share financed by owners.", "x"),
    "debt_to_equity": ("Debt to equity", "Solvency", "Total liabilities / Equity", "< 1 - 1.5",
                       "Leverage: lei/$ of debt per 1 of own capital.", "x"),
    "interest_coverage": ("Interest coverage", "Solvency", "Operating profit / Financial expenses", "> 3",
                          "How many times operating profit covers interest.", "x"),
    "receivables_turnover": ("Account receivables turnover", "Activity", "Revenue / ST receivables", "higher is faster",
                             "How many times per year customers pay their debts. 365 / turnover = collection days.", "x"),
    "receivables_days": ("Collection period (days)", "Activity", "365 / Receivables turnover", "lower is better",
                         "Average days customers take to pay.", "days"),
    "dts_turnover": ("ST debt (DTS) turnover", "Activity", "Revenue / ST debt", "industry-specific",
                     "How many times per year sales cover short-term debts.", "x"),
    "asset_turnover": ("Asset turnover", "Activity", "Revenue / Total assets", "higher is better",
                       "Sales generated per 1 of assets.", "x"),
}


def compute_ratios(d: pd.DataFrame) -> pd.DataFrame:
    g = d.loc
    avg_assets = (g["total_assets"] + g["total_assets"].shift(1)) / 2
    avg_assets = avg_assets.fillna(g["total_assets"])  # first year: no previous year, use year-end (as in template)
    debts = g["current_liabilities"] + g["noncurrent_liabilities"]
    r = {
        "return_on_sales": _div(g["pretax_profit"], g["revenue"]) * 100,
        "roa": _div(g["pretax_profit"], avg_assets) * 100,
        "roe": _div(g["net_profit"], g["equity"]) * 100,
        "gross_margin": _div(g["gross_profit"], g["revenue"]) * 100,
        "net_margin": _div(g["net_profit"], g["revenue"]) * 100,
        "abs_liquidity": _div(g["cash"], g["current_liabilities"]),
        "quick_liquidity": _div(g["cash"] + g["st_investments"].fillna(0) + g["receivables"].fillna(0),
                                g["current_liabilities"]),
        "current_liquidity": _div(g["current_assets"], g["current_liabilities"]),
        "general_solvency": _div(g["total_assets"], debts),
        "debt_ratio": _div(debts, g["total_assets"]),
        "debt_to_equity": _div(g["total_liabilities"], g["equity"]),
        "interest_coverage": _div(g["operating_profit"], g["financial_expenses"]),
        "receivables_turnover": _div(g["revenue"], g["receivables"]),
        "dts_turnover": _div(g["revenue"], g["current_liabilities"]),
        "asset_turnover": _div(g["revenue"], g["total_assets"]),
    }
    r["receivables_days"] = _div(pd.Series(365.0, index=d.columns), r["receivables_turnover"])
    return pd.DataFrame(r).T.reindex(list(RATIOS))


# ---------------------------------------------------------------------------
# Bankruptcy-risk models (Solvency.xlsx: Altman, Taffler, Conan-Holder)
# ---------------------------------------------------------------------------
SCORE_INFO = {
    "altman_course": {
        "label": "Altman Z (course version, Solvency.xlsx)",
        "formula": "Z = 3.3*X1 + 1.0*X2 + 0.6*X3 + 1.4*X4 + 1.2*X5\n"
                   "X1 = Gross profit / Total assets\nX2 = Sales / Total assets\n"
                   "X3 = Equity / Total debt\nX4 = Retained profit / Total assets\nX5 = Current assets / Total assets",
        "zones": [(-math.inf, 1.8, "DISTRESS"), (1.8, 3.0, "DIFFICULT (grey zone)"), (3.0, math.inf, "SOLVENT")],
    },
    "altman_original": {
        "label": "Altman Z (original 1968)",
        "formula": "Z = 1.2*X1 + 1.4*X2 + 3.3*X3 + 0.6*X4 + 1.0*X5\n"
                   "X1 = (Current assets - ST debt) / Total assets   (working capital)\n"
                   "X2 = Retained earnings / Total assets\nX3 = EBIT (operating profit) / Total assets\n"
                   "X4 = Market value of equity / Total liabilities (book equity if not listed)\nX5 = Sales / Total assets",
        "zones": [(-math.inf, 1.81, "DISTRESS"), (1.81, 2.99, "GREY ZONE"), (2.99, math.inf, "SAFE")],
    },
    "taffler": {
        "label": "Taffler Z",
        "formula": "Z = 0.53*X1 + 0.13*X2 + 0.18*X3 + 0.16*X4\n"
                   "X1 = Profit before tax / ST debt\nX2 = Current assets / Total liabilities\n"
                   "X3 = ST debt / Total assets\nX4 = Sales / Total assets",
        "zones": [(-math.inf, 0.2, "HIGH bankruptcy risk"), (0.2, 0.3, "UNCERTAIN"), (0.3, math.inf, "LOW risk")],
    },
    "holder": {
        "label": "Conan-Holder Z",
        "formula": "Z = 0.24*X1 + 0.22*X2 + 0.16*X3 - 0.87*X4 - 0.10*X5\n"
                   "X1 = EBITDA (gross operating surplus) / Total debt\nX2 = Permanent capital / Total assets\n"
                   "X3 = (Current assets - Inventories) / Total assets\nX4 = Financial expenses / Sales\n"
                   "X5 = Personnel costs / Value added  (value added ~ EBITDA + personnel costs)\n"
                   "Permanent capital = Equity + LT debt",
        "zones": [(-math.inf, 0.04, "DANGER (failure prob. > 65%)"), (0.04, 0.16, "ALERT (30-65%)"),
                  (0.16, math.inf, "GOOD (< 10-30%)")],
    },
}


def interpret(model: str, z: float) -> str:
    if z is None or (isinstance(z, float) and math.isnan(z)):
        return "n/a"
    for lo, hi, label in SCORE_INFO[model]["zones"]:
        if lo <= z < hi:
            return label
    return "n/a"


def compute_scores(d: pd.DataFrame, market_cap: float | None = None) -> tuple[pd.DataFrame, dict]:
    g = {k: d.loc[k].fillna(0) if k in ("st_investments", "inventory", "financial_expenses", "rd", "other_opex")
         else d.loc[k] for k in d.index}
    ta, cl, ncl = g["total_assets"], g["current_liabilities"], g["noncurrent_liabilities"]
    debts = cl + ncl
    parts = {}

    unreparted = g["retained_earnings"]
    a = {"X1": _div(g["gross_profit"], ta), "X2": _div(g["revenue"], ta), "X3": _div(g["equity"], debts),
         "X4": _div(unreparted, ta), "X5": _div(g["current_assets"], ta)}
    parts["altman_course"] = a
    z_course = 3.3 * a["X1"] + 1.0 * a["X2"] + 0.6 * a["X3"] + 1.4 * a["X4"] + 1.2 * a["X5"]

    equity_value = g["equity"].copy()
    if market_cap:  # market cap is today's value - apply to latest year only, book equity for history
        equity_value.iloc[-1] = market_cap
    o = {"X1": _div(g["current_assets"] - cl, ta), "X2": _div(g["retained_earnings"], ta),
         "X3": _div(g["operating_profit"], ta), "X4": _div(equity_value, debts), "X5": _div(g["revenue"], ta)}
    parts["altman_original"] = o
    z_orig = 1.2 * o["X1"] + 1.4 * o["X2"] + 3.3 * o["X3"] + 0.6 * o["X4"] + 1.0 * o["X5"]

    t = {"X1": _div(g["pretax_profit"], cl), "X2": _div(g["current_assets"], debts),
         "X3": _div(cl, ta), "X4": _div(g["revenue"], ta)}
    parts["taffler"] = t
    z_taff = 0.53 * t["X1"] + 0.13 * t["X2"] + 0.18 * t["X3"] + 0.16 * t["X4"]

    pers = g["personnel_costs"]
    value_added = g["ebitda"] + pers.fillna(0)
    h = {"X1": _div(g["ebitda"], debts), "X2": _div(g["equity"] + ncl, ta),
         "X3": _div(g["current_assets"] - g["inventory"], ta), "X4": _div(g["financial_expenses"], g["revenue"]),
         "X5": _div(pers, value_added).fillna(0)}
    parts["holder"] = h
    z_hold = 0.24 * h["X1"] + 0.22 * h["X2"] + 0.16 * h["X3"] - 0.87 * h["X4"] - 0.10 * h["X5"]

    scores = pd.DataFrame({"altman_course": z_course, "altman_original": z_orig,
                           "taffler": z_taff, "holder": z_hold}).T
    return scores, parts


def vertical_analysis(d: pd.DataFrame) -> pd.DataFrame:
    """Each balance-sheet line as % of total assets (structure analysis)."""
    keys = ["cash", "st_investments", "receivables", "inventory", "current_assets",
            "current_liabilities", "noncurrent_liabilities", "equity"]
    return d.loc[keys].div(d.loc["total_assets"]) * 100


def horizontal_analysis(d: pd.DataFrame) -> pd.DataFrame:
    """Year-over-year change % (dynamics analysis)."""
    return d.pct_change(axis=1, fill_method=None) * 100
