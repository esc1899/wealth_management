#!/bin/bash
# Launch Wealth Management app via Streamlit
# Force arm64 on Apple Silicon

exec arch -arm64 /Users/erik/Projects/wealth_management/.venv/bin/python -m streamlit run app.py
