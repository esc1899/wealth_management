#!/bin/bash
set -e

PROJECT_DIR="$(dirname "$0")"
LOG_DIR="$HOME/.wealth-management"
mkdir -p "$LOG_DIR"

# Pause background agent during development
launchctl unload ~/Library/LaunchAgents/com.erik.wealth-management.plist 2>/dev/null || true

cd "$PROJECT_DIR"

# Verify venv exists
if [ ! -f ".venv/bin/activate" ]; then
    echo "Error: .venv not found. Run: python -m venv .venv && .venv/bin/pip install -r requirements.txt"
    sleep 5
    exit 1
fi

# Activate virtual environment
source .venv/bin/activate

# Kill any existing Streamlit instances
pkill -f "streamlit run" 2>/dev/null || true
sleep 1

# Start Streamlit in background, immune to terminal closure
nohup streamlit run app.py > "$LOG_DIR/streamlit.log" 2>&1 &
STREAMLIT_PID=$!

# Wait for Streamlit to start (check if server is ready)
sleep 3
for i in {1..10}; do
    if curl -s http://localhost:8501/_stcore/health > /dev/null 2>&1; then
        echo "Streamlit started successfully (PID: $STREAMLIT_PID)"
        break
    fi
    if [ $i -eq 10 ]; then
        echo "Warning: Streamlit may not have started properly. Check: $LOG_DIR/streamlit.log"
        sleep 2
    else
        sleep 1
    fi
done

# Open browser to the Streamlit app
open http://localhost:8501

# Resume background agent
launchctl load ~/Library/LaunchAgents/com.erik.wealth-management.plist 2>/dev/null || true

echo "App started. Browser opened. Close this window to continue."
sleep 2
exit 0
