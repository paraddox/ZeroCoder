#!/bin/bash
cd "$(dirname "$0")"
# ZeroCoder UI Launcher for Unix/Linux/macOS
# This script launches the web UI for the autonomous coding agent.

echo ""
echo "===================================="
echo "  ZeroCoder UI"
echo "===================================="
echo ""

# Check if Python is available
if ! command -v python3 &> /dev/null; then
    if ! command -v python &> /dev/null; then
        echo "ERROR: Python not found"
        echo "Please install Python from https://python.org"
        exit 1
    fi
    PYTHON_CMD="python"
else
    PYTHON_CMD="python3"
fi

# Check if venv exists, create if not
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    $PYTHON_CMD -m venv venv
fi

# Activate the virtual environment
source venv/bin/activate

# Install dependencies
echo "Installing dependencies..."
pip install -r requirements.txt --quiet

PID_FILE="/tmp/zerocoder-ui.pid"

# Check for --stop flag
if [[ " $* " == *" --stop "* ]] || [[ " $* " == *" -s "* ]]; then
    echo "Stopping ZeroCoder UI..."

    # Stop all zerocoder containers FIRST (before killing server)
    echo "Stopping zerocoder containers..."
    ZEROCODER_CONTAINERS=$(docker ps -q --filter "name=zerocoder-" 2>/dev/null)
    if [ ! -z "$ZEROCODER_CONTAINERS" ]; then
        docker stop $ZEROCODER_CONTAINERS 2>/dev/null && echo "Containers stopped"
    fi

    # Kill by PID file if exists
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if kill -0 "$PID" 2>/dev/null; then
            echo "Sending SIGTERM to process $PID..."
            kill -TERM "$PID" 2>/dev/null
            # Wait up to 10 seconds for graceful shutdown
            for i in {1..10}; do
                if ! kill -0 "$PID" 2>/dev/null; then
                    echo "Process $PID stopped gracefully"
                    break
                fi
                sleep 1
            done
            # Force kill if still running
            if kill -0 "$PID" 2>/dev/null; then
                echo "Force killing process $PID"
                kill -9 "$PID" 2>/dev/null
            fi
        fi
        rm -f "$PID_FILE"
    fi
    # Also stop any remaining uvicorn processes
    UVICORN_PIDS=$(pgrep -f "uvicorn server.main:app")
    if [ ! -z "$UVICORN_PIDS" ]; then
        echo "Stopping uvicorn processes: $UVICORN_PIDS"
        for PID in $UVICORN_PIDS; do
            kill -TERM "$PID" 2>/dev/null
            # Wait up to 10 seconds
            for i in {1..10}; do
                if ! kill -0 "$PID" 2>/dev/null; then
                    break
                fi
                sleep 1
            done
            # Force kill if still running
            if kill -0 "$PID" 2>/dev/null; then
                kill -9 "$PID" 2>/dev/null
            fi
        done
        echo "Stopped uvicorn processes"
    fi
    exit 0
fi

# Check for -bg flag to run in background
if [[ " $* " == *" -bg "* ]] || [[ " $* " == *" --background "* ]]; then
    # Remove -bg/--background from args before passing to start-app.py
    ARGS=$(echo "$@" | sed 's/-bg//g' | sed 's/--background//g')
    echo "Starting server in background..."
    nohup python start-app.py $ARGS > /tmp/zerocoder-ui.log 2>&1 &
    BG_PID=$!
    echo "$BG_PID" > "$PID_FILE"
    sleep 2  # Wait for uvicorn to start
    # Find the actual uvicorn PID
    UVICORN_PID=$(pgrep -f "uvicorn server.main:app" | head -1)
    echo "Shell PID: $BG_PID"
    echo "Uvicorn PID: $UVICORN_PID"
    echo "Log file: /tmp/zerocoder-ui.log"
    echo ""
    echo "UI available at: http://localhost:8000"
    echo "To stop: ./start-app.sh --stop"
else
    # Run in foreground
    python start-app.py "$@"
fi
