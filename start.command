#!/bin/bash
# Dock launcher: ensure background service is running and open browser

PLIST="$HOME/Library/LaunchAgents/com.erik.wealth-management.plist"
SERVICE_URL="http://localhost:6655"
MAX_WAIT=5

# Ensure LaunchAgent is loaded (starts the background service)
if [ -f "$PLIST" ]; then
    launchctl list com.erik.wealth-management > /dev/null 2>&1 || launchctl load "$PLIST"
fi

# Wait for service to be ready (max 5 seconds)
for i in $(seq 1 $MAX_WAIT); do
    if curl -s "$SERVICE_URL/_stcore/health" > /dev/null 2>&1; then
        break
    fi
    sleep 1
done

# Open browser
open "$SERVICE_URL"
exit 0
