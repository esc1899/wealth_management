#!/bin/bash
cd "$(dirname "$0")"
source .venv/bin/activate
pkill -f "streamlit run" 2>/dev/null || true
streamlit run app.py
