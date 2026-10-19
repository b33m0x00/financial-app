#!/usr/bin/env bash
# First run creates .venv and installs packages; then opens the app at http://localhost:8501
cd "$(dirname "$0")"
[ -d .venv ] || { python3 -m venv .venv && .venv/bin/pip install -q -r requirements.txt; }
.venv/bin/streamlit run app.py
