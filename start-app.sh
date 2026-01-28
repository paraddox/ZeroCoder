#!/bin/bash
cd "$(dirname "$0")"
# ZeroCoder UI Launcher for Unix/Linux/macOS
# This script launches the web UI for the autonomous coding agent.

# Load environment variables from .env file if it exists
# Note: PORT is determined dynamically, don't load from .env
if [ -f ".env" ]; then
    # Source each line to properly handle tilde expansion
    while IFS='=' read -r key value; do
        # Skip empty lines and comments
        [[ -z "$key" || "$key" =~ ^# ]] && continue
        # Skip PORT - it's determined dynamically
        [[ "$key" == "PORT" ]] && continue
        # Expand tilde in value
        value="${value/#\~/$HOME}"
        export "$key=$value"
    done < .env
fi

# Port file written by the server
PORT_FILE="/tmp/zerocoder-port.txt"

echo ""
echo "===================================="
echo "  ZeroCoder UI"
echo "===================================="
echo ""

# Detect package manager (pnpm preferred)
if command -v pnpm &> /dev/null; then
    PKG_MANAGER="pnpm"
    PKG_CMD="pnpm"
    PKG_INSTALL="pnpm install"
    PKG_RUN="pnpm run"
elif command -v npm &> /dev/null; then
    PKG_MANAGER="npm"
    PKG_CMD="npm"
    PKG_INSTALL="npm install"
    PKG_RUN="npm run"
else
    echo "ERROR: Neither pnpm nor npm found"
    echo "Please install pnpm (https://pnpm.io/installation) or Node.js (https://nodejs.org)"
    exit 1
fi

echo "Using package manager: $PKG_MANAGER"

# Check if Node.js is available
if ! command -v node &> /dev/null; then
    echo "ERROR: Node.js not found"
    echo "Please install Node.js from https://nodejs.org"
    exit 1
fi

NODE_VERSION=$(node --version)
echo "Node.js version: $NODE_VERSION"

# Configure git hooks (auto-setup on first run)
if [ "$(git config core.hooksPath)" != ".githooks" ]; then
    echo "Configuring git hooks..."
    git config core.hooksPath .githooks
fi

# Install dependencies at root (for shared packages)
echo "Installing root dependencies..."
$PKG_INSTALL

# Install dependencies for packages/server
echo "Installing server dependencies..."
cd packages/server
$PKG_INSTALL
cd ../..

# Install dependencies for UI (if UI directory exists)
if [ -d "ui" ]; then
    echo "Installing UI dependencies..."
    cd ui
    $PKG_INSTALL
    cd ..
fi

# Always build Docker image to pick up any changes
# Uses BuildKit with SSH key secret for git clone support
DOCKER_IMAGE="zerocoder-project"
SSH_KEY_PATH="${GIT_SSH_KEY_PATH:-$HOME/.ssh/id_ed25519}"

echo "Building Docker image '$DOCKER_IMAGE' with BuildKit..."

# Check if SSH key exists
if [ ! -f "$SSH_KEY_PATH" ]; then
    echo "WARNING: SSH key not found at $SSH_KEY_PATH"
    echo "Container will not be able to clone private repositories"
    echo "Set GIT_SSH_KEY_PATH environment variable to specify a different key"
    # Build without SSH key secret
    DOCKER_BUILDKIT=1 docker build -f Dockerfile.project -t "$DOCKER_IMAGE" .
else
    # Build with SSH key secret (key is copied securely, not stored in image layers)
    DOCKER_BUILDKIT=1 docker build \
        --secret id=ssh_key,src="$SSH_KEY_PATH" \
        -f Dockerfile.project -t "$DOCKER_IMAGE" .
fi

if [ $? -ne 0 ]; then
    echo "ERROR: Failed to build Docker image"
    exit 1
fi
echo "Docker image built successfully"

PID_FILE="/tmp/zerocoder-ui.pid"
SERVER_PID=""
VITE_PID=""

# Cleanup function for graceful shutdown
cleanup() {
    echo ""
    echo "Shutting down ZeroCoder UI..."

    # Stop the server process if running
    if [ ! -z "$SERVER_PID" ]; then
        echo "Stopping server process (PID: $SERVER_PID)..."
        kill -TERM "$SERVER_PID" 2>/dev/null
        # Wait a bit for graceful shutdown
        sleep 2
        # Force kill if still running
        if kill -0 "$SERVER_PID" 2>/dev/null; then
            kill -9 "$SERVER_PID" 2>/dev/null
        fi
    fi

    # Stop the Vite process if running
    if [ ! -z "$VITE_PID" ]; then
        echo "Stopping Vite process (PID: $VITE_PID)..."
        kill -TERM "$VITE_PID" 2>/dev/null
        sleep 1
        if kill -0 "$VITE_PID" 2>/dev/null; then
            kill -9 "$VITE_PID" 2>/dev/null
        fi
    fi

    # Remove all zerocoder containers
    echo "Removing zerocoder containers..."
    ZEROCODER_CONTAINERS=$(docker ps -aq --filter "name=zerocoder-" 2>/dev/null)
    if [ ! -z "$ZEROCODER_CONTAINERS" ]; then
        docker rm -f $ZEROCODER_CONTAINERS 2>/dev/null && echo "Containers removed"
    fi

    # Stop any remaining Node.js server processes
    NODE_PIDS=$(pgrep -f "node.*packages/server")
    if [ ! -z "$NODE_PIDS" ]; then
        echo "Stopping Node.js server processes..."
        for PID in $NODE_PIDS; do
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
    # Also stop any remaining Node.js server processes
    NODE_PIDS=$(pgrep -f "node.*packages/server")
    if [ ! -z "$NODE_PIDS" ]; then
        echo "Stopping Node.js server processes: $NODE_PIDS"
        for PID in $NODE_PIDS; do
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
        echo "Stopped Node.js server processes"
    fi
    # Also stop any Vite processes
    VITE_PIDS=$(pgrep -f "vite")
    if [ ! -z "$VITE_PIDS" ]; then
        echo "Stopping Vite processes: $VITE_PIDS"
        for PID in $VITE_PIDS; do
            kill -TERM "$PID" 2>/dev/null
            sleep 1
            if kill -0 "$PID" 2>/dev/null; then
                kill -9 "$PID" 2>/dev/null
            fi
        done
        echo "Stopped Vite processes"
    fi
    exit 0
fi

# Check for --restart flag (restart server only, preserve containers)
if [[ " $* " == *" --restart "* ]] || [[ " $* " == *" -r "* ]]; then
    echo "Restarting ZeroCoder server (preserving containers)..."

    # Kill server processes only (not containers)
    NODE_PIDS=$(pgrep -f "node.*packages/server")
    if [ ! -z "$NODE_PIDS" ]; then
        echo "Stopping Node.js server processes: $NODE_PIDS"
        for PID in $NODE_PIDS; do
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
        $PKG_RUN build
        cd ..
        echo "UI rebuilt"
    fi

    # Cleanup for restart mode - DON'T touch containers
    cleanup_restart() {
        echo ""
        echo "Shutting down server (containers preserved)..."
        if [ ! -z "$SERVER_PID" ]; then
            kill -TERM "$SERVER_PID" 2>/dev/null
            sleep 2
            if kill -0 "$SERVER_PID" 2>/dev/null; then
                kill -9 "$SERVER_PID" 2>/dev/null
            fi
        fi
        NODE_PIDS=$(pgrep -f "node.*packages/server")
        if [ ! -z "$NODE_PIDS" ]; then
            for PID in $NODE_PIDS; do
                kill -TERM "$PID" 2>/dev/null
            done
        fi
        echo "Server stopped (containers still running)"
        exit 0
    }
    trap cleanup_restart SIGINT SIGTERM

    # Start server in foreground
    echo "Starting server..."
    cd packages/server
    $PKG_RUN start &
    SERVER_PID=$!
    cd ..
    echo "Server PID: $SERVER_PID"
    wait $SERVER_PID
    exit 0
fi

# Function to find an available port
find_available_port() {
    local start_port=${1:-8888}
    local max_attempts=${2:-10}
    local port=$start_port

    while [ $port -lt $((start_port + max_attempts)) ]; do
        if ! nc -z 127.0.0.1 $port 2>/dev/null; then
            echo $port
            return 0
        fi
        port=$((port + 1))
    done

    echo "ERROR: No available ports found in range $start_port-$((start_port + max_attempts))" >&2
    return 1
}

# Function to start the TypeScript server
start_server() {
    local port=$1
    local dev_mode=$2

    export PORT=$port
    echo "$port" > "$PORT_FILE"

    if [ "$dev_mode" = "true" ]; then
        echo "Starting development server on port $port..."
        cd packages/server
        $PKG_RUN dev &
        SERVER_PID=$!
        cd ..
    else
        echo "Starting production server on port $port..."
        # Build first
        cd packages/server
        $PKG_RUN build
        $PKG_RUN start &
        SERVER_PID=$!
        cd ..
    fi
}

# Check for --dev flag
DEV_MODE=false
if [[ " $* " == *" --dev "* ]] || [[ " $* " == *" -d "* ]]; then
    DEV_MODE=true
fi

# Check for -bg flag to run in background
if [[ " $* " == *" -bg "* ]] || [[ " $* " == *" --background "* ]]; then
    echo "Starting server in background..."

    PORT=$(find_available_port)
    if [ $? -ne 0 ]; then
        echo "ERROR: Could not find an available port"
        exit 1
    fi

    start_server $PORT false

    echo "$SERVER_PID" > "$PID_FILE"
    sleep 3

    echo "Server PID: $SERVER_PID"
    echo "Log file: /tmp/zerocoder-ui.log"
    echo ""
    echo "UI available at: http://localhost:$PORT"
    echo "To stop: ./start-app.sh --stop"
else
    # Run in foreground with signal handling
    PORT=$(find_available_port)
    if [ $? -ne 0 ]; then
        echo "ERROR: Could not find an available port"
        exit 1
    fi

    start_server $PORT $DEV_MODE

    echo "Server PID: $SERVER_PID"
    echo ""
    echo "===================================="
    if [ "$DEV_MODE" = "true" ]; then
        echo "  Development mode active"
        echo "  API: http://localhost:$PORT"
        echo "  Press Ctrl+C to stop"
    else
        echo "  Server running at http://localhost:$PORT"
        echo "  Press Ctrl+C to stop"
    fi
    echo "===================================="
    echo ""

    # Wait for the server process (will be interrupted by Ctrl-C)
    wait $SERVER_PID
fi
