#!/bin/bash
# Pause background agent during development
launchctl unload ~/Library/LaunchAgents/com.erik.wealth-management.plist 2>/dev/null || true

cd "$(dirname "$0")"
source .venv/bin/activate
pkill -f "streamlit run" 2>/dev/null || true
streamlit run app.py

# Resume background agent when done
launchctl load ~/Library/LaunchAgents/com.erik.wealth-management.plist
