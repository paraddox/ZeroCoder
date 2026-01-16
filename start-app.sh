#!/bin/bash
cd "$(dirname "$0")"
# ZeroCoder UI Launcher for Unix/Linux/macOS
# This script launches the web UI for the autonomous coding agent.

# Load environment variables from .env file if it exists
if [ -f ".env" ]; then
    # Source each line to properly handle tilde expansion
    while IFS='=' read -r key value; do
        # Skip empty lines and comments
        [[ -z "$key" || "$key" =~ ^# ]] && continue
        # Expand tilde in value
        value="${value/#\~/$HOME}"
        export "$key=$value"
    done < .env
fi

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

# Check if Docker image exists, build if not
DOCKER_IMAGE="zerocoder-project"
if ! docker image inspect "$DOCKER_IMAGE" &> /dev/null; then
    echo "Docker image '$DOCKER_IMAGE' not found, building..."
    docker build -f Dockerfile.project -t "$DOCKER_IMAGE" .
    if [ $? -ne 0 ]; then
        echo "ERROR: Failed to build Docker image"
        exit 1
    fi
    echo "Docker image built successfully"
else
    echo "Docker image '$DOCKER_IMAGE' found"
fi

PID_FILE="/tmp/zerocoder-ui.pid"
PYTHON_PID=""

# Cleanup function for graceful shutdown
cleanup() {
    echo ""
    echo "Shutting down ZeroCoder UI..."

    # Stop the Python process if running
    if [ ! -z "$PYTHON_PID" ]; then
        echo "Stopping Python process (PID: $PYTHON_PID)..."
        kill -TERM "$PYTHON_PID" 2>/dev/null
        # Wait a bit for graceful shutdown
        sleep 2
        # Force kill if still running
        if kill -0 "$PYTHON_PID" 2>/dev/null; then
            kill -9 "$PYTHON_PID" 2>/dev/null
        fi
    fi

    # Remove all zerocoder containers
    echo "Removing zerocoder containers..."
    ZEROCODER_CONTAINERS=$(docker ps -aq --filter "name=zerocoder-" 2>/dev/null)
    if [ ! -z "$ZEROCODER_CONTAINERS" ]; then
        docker rm -f $ZEROCODER_CONTAINERS 2>/dev/null && echo "Containers removed"
    fi

    # Stop any remaining uvicorn processes
    UVICORN_PIDS=$(pgrep -f "uvicorn server.main:app")
    if [ ! -z "$UVICORN_PIDS" ]; then
        echo "Stopping uvicorn processes..."
        for PID in $UVICORN_PIDS; do
            kill -TERM "$PID" 2>/dev/null
        done
    fi

    echo "Shutdown complete"
    exit 0
}

# Set up signal traps for clean shutdown on Ctrl-C
trap cleanup SIGINT SIGTERM

# Check for --stop flag
if [[ " $* " == *" --stop "* ]] || [[ " $* " == *" -s "* ]]; then
    echo "Stopping ZeroCoder UI..."

    # Remove all zerocoder containers FIRST (before killing server)
    echo "Removing zerocoder containers..."
    ZEROCODER_CONTAINERS=$(docker ps -aq --filter "name=zerocoder-" 2>/dev/null)
    if [ ! -z "$ZEROCODER_CONTAINERS" ]; then
        docker rm -f $ZEROCODER_CONTAINERS 2>/dev/null && echo "Containers removed"
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

# Check for --restart flag (restart server only, preserve containers)
if [[ " $* " == *" --restart "* ]] || [[ " $* " == *" -r "* ]]; then
    echo "Restarting ZeroCoder server (preserving containers)..."

    # Kill server processes only (not containers)
    UVICORN_PIDS=$(pgrep -f "uvicorn server.main:app")
    if [ ! -z "$UVICORN_PIDS" ]; then
        echo "Stopping uvicorn processes: $UVICORN_PIDS"
        for PID in $UVICORN_PIDS; do
            kill -TERM "$PID" 2>/dev/null
            for i in {1..5}; do
                if ! kill -0 "$PID" 2>/dev/null; then
                    break
                fi
                sleep 1
            done
            if kill -0 "$PID" 2>/dev/null; then
                kill -9 "$PID" 2>/dev/null
            fi
        done
        echo "Server stopped"
    fi

    # Rebuild UI
    echo "Rebuilding UI..."
    if [ -d "ui" ]; then
        cd ui
        npm run build --silent
        cd ..
        echo "UI rebuilt"
    fi

    # Cleanup for restart mode - DON'T touch containers
    cleanup_restart() {
        echo ""
        echo "Shutting down server (containers preserved)..."
        if [ ! -z "$PYTHON_PID" ]; then
            kill -TERM "$PYTHON_PID" 2>/dev/null
            sleep 2
            if kill -0 "$PYTHON_PID" 2>/dev/null; then
                kill -9 "$PYTHON_PID" 2>/dev/null
            fi
        fi
        UVICORN_PIDS=$(pgrep -f "uvicorn server.main:app")
        if [ ! -z "$UVICORN_PIDS" ]; then
            for PID in $UVICORN_PIDS; do
                kill -TERM "$PID" 2>/dev/null
            done
        fi
        echo "Server stopped (containers still running)"
        exit 0
    }
    trap cleanup_restart SIGINT SIGTERM

    # Start server in foreground
    echo "Starting server..."
    python start-app.py &
    PYTHON_PID=$!
    echo "Python PID: $PYTHON_PID"
    wait $PYTHON_PID
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
    # Run in foreground with signal handling
    python start-app.py "$@" &
    PYTHON_PID=$!
    echo "Python PID: $PYTHON_PID"

    # Wait for the Python process (will be interrupted by Ctrl-C)
    wait $PYTHON_PID
fi
