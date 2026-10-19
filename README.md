# Company Financial Analysis

Type a company name -> app pulls balance sheet + income statement from Yahoo Finance
and computes the indicators from the course Excel templates, with charts, tables,
formula explanations and an Excel export where every ratio is a live formula.

## Run

```bash
./run.sh          # first run installs packages, then opens http://localhost:8501
```

## Tabs

| Tab | Content |
|---|---|
| Statements | Balance sheet, income statement, dividends; horizontal analysis (YoY %) |
| Profit & costs | Revenue -> net profit bars, cost structure (sheet *Costs analysis*), margins |
| Balance structure | Assets vs liabilities+equity stacks, vertical analysis (% of total assets) |
| Ratios | Profitability, liquidity, solvency, activity - table + chart with norm band |
| Bankruptcy risk | Altman (course + original), Taffler, Conan-Holder with zones |
| Formulas explained | How to read statements, every formula + bond/CAPM/break-even formulas |
| Export | PDF report (summary + automatic commentary, charts, ratio tables, Z-scores), study guide PDF, flashcards CSV, `.xlsx` with live formulas, CSV |

Manual entry mode: for companies not on Yahoo (e.g. Moldovan/Romanian SMEs) type the
numbers yourself, or upload a Data sheet exported by the app.

## Files

- `fin.py` - data download (yfinance), input definitions, ratio + Z-score formulas
- `excel_export.py` - builds the Excel workbook with formulas
- `report.py` - PDF report, study guide (glossary, formulas, worked examples, solved course exercises, self-test), flashcards
- `app.py` - Streamlit web UI

## Notes / limits

- Yahoo gives ~4 annual years. Banks/insurers have no current/non-current split, so liquidity and Z-scores are blank.
- Yahoo rarely reports personnel costs -> Conan-Holder X5 = 0 unless entered manually.
- "Debt on ST" = current liabilities, "Debt on LT" = non-current liabilities (as in the template).
