#!/bin/bash
cd "$(dirname "$0")"
# ZeroCoder UI Launcher for Unix/Linux/macOS
# This script launches the web UI for the autonomous coding agent.

# Load environment variables from .env file if it exists
# Note: PORT is determined dynamically by start-app.py, don't load from .env
if [ -f ".env" ]; then
    # Source each line to properly handle tilde expansion
    while IFS='=' read -r key value; do
        # Skip empty lines and comments
        [[ -z "$key" || "$key" =~ ^# ]] && continue
        # Skip PORT - it's determined dynamically by start-app.py
        [[ "$key" == "PORT" ]] && continue
        # Expand tilde in value
        value="${value/#\~/$HOME}"
        export "$key=$value"
    done < .env
fi

# Port file written by start-app.py
PORT_FILE="/tmp/zerocoder-port.txt"

echo ""
echo "===================================="
echo "  ZeroCoder UI"
echo "===================================="
echo ""

# Check if Python is available (prefer Homebrew Python on macOS)
if [ -x "/opt/homebrew/bin/python3" ]; then
    # macOS ARM Homebrew
    PYTHON_CMD="/opt/homebrew/bin/python3"
elif [ -x "/usr/local/bin/python3" ]; then
    # macOS Intel Homebrew or Linux /usr/local
    PYTHON_CMD="/usr/local/bin/python3"
elif command -v python3 &> /dev/null; then
    PYTHON_CMD="python3"
elif command -v python &> /dev/null; then
    PYTHON_CMD="python"
else
    echo "ERROR: Python not found"
    echo "Please install Python from https://python.org"
    exit 1
fi

# Check if venv exists, create if not
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    $PYTHON_CMD -m venv venv
fi

# Activate the virtual environment
source venv/bin/activate

# Configure git hooks (auto-setup on first run)
if [ "$(git config core.hooksPath)" != ".githooks" ]; then
    echo "Configuring git hooks..."
    git config core.hooksPath .githooks
fi

# Install dependencies
echo "Installing dependencies..."
pip install -r requirements.txt --quiet

# Check E2B configuration
echo "Checking E2B configuration..."

# Verify E2B API key is set
if [ -z "$E2B_API_KEY" ]; then
    echo "WARNING: E2B_API_KEY not set in environment"
    echo "E2B sandboxes will not work without an API key"
    echo "Set E2B_API_KEY in your .env file"
fi

# Check for SSH key (needed for git clone in sandboxes)
SSH_KEY_PATH="${GIT_SSH_KEY_PATH:-$HOME/.ssh/id_ed25519}"
if [ ! -f "$SSH_KEY_PATH" ]; then
    echo "WARNING: SSH key not found at $SSH_KEY_PATH"
    echo "Sandboxes will not be able to clone private repositories"
    echo "Set GIT_SSH_KEY_PATH environment variable to specify a different key"
else
    # Base64 encode SSH key for E2B if not already set
    if [ -z "$SSH_PRIVATE_KEY_BASE64" ]; then
        export SSH_PRIVATE_KEY_BASE64=$(base64 -w 0 "$SSH_KEY_PATH" 2>/dev/null || base64 "$SSH_KEY_PATH")
        echo "SSH key loaded for E2B sandboxes"
    fi
fi

echo "E2B configuration ready"

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

    # E2B sandboxes are cleaned up by the server's lifespan handler
    # No local container cleanup needed

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

    # E2B sandboxes are cleaned up by the server's lifespan handler
    # No local container cleanup needed

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
    sleep 3  # Wait for uvicorn to start and port file to be written
    # Find the actual uvicorn PID
    UVICORN_PID=$(pgrep -f "uvicorn server.main:app" | head -1)
    echo "Shell PID: $BG_PID"
    echo "Uvicorn PID: $UVICORN_PID"
    echo "Log file: /tmp/zerocoder-ui.log"
    echo ""
    # Read port from file written by start-app.py
    if [ -f "$PORT_FILE" ]; then
        ACTUAL_PORT=$(cat "$PORT_FILE")
        echo "UI available at: http://localhost:$ACTUAL_PORT"
    else
        echo "UI available at: http://localhost:8888 (port file not found)"
    fi
    echo "To stop: ./start-app.sh --stop"
else
    # Run in foreground with signal handling
    python start-app.py "$@" &
    PYTHON_PID=$!
    echo "Python PID: $PYTHON_PID"

    # Wait for the Python process (will be interrupted by Ctrl-C)
    wait $PYTHON_PID
fi
