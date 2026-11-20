#!/bin/bash
# ==============================================================
# JobFlow AI - 1-Click macOS Launcher (Double-clickable)
# ==============================================================

# Change to the directory where this script is located
cd "$(dirname "$0")" || exit 1

PORT=8085
URL="http://localhost:$PORT"

echo "=========================================================="
echo " Starting JobFlow AI Multi-Agent Application Hub"
echo " Dashboard URL: $URL"
echo " Connected Email: taaryan.official@gmail.com"
echo "=========================================================="

# Check if .venv exists
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment .venv..."
    python3 -m venv .venv
fi

# Open dashboard in default browser after 1.5 seconds in background
(sleep 2 && open "$URL") &

# Start FastAPI backend (which also serves the responsive frontend)
echo "Starting unified server on port $PORT..."
echo "Tip: Press Ctrl+C in this terminal window anytime to completely stop the application."
echo "=========================================================="
./.venv/bin/uvicorn app.server:app --host 127.0.0.1 --port $PORT --reload
