#!/bin/bash
#
# ZeroCoder Daemon Installation Script
# =====================================
#
# Installs all dependencies and sets up the daemon on a remote machine.
# Run with: curl -fsSL <url>/install.sh | bash
#
# What this script does:
# 1. Install Node.js via nvm (if not installed)
# 2. Install Rust and beads CLI (if not installed)
# 3. Install Claude Code CLI (if not installed)
# 4. Clone/update ZeroCoder repo and build daemon
# 5. Start the daemon

set -e

# Configuration
ZEROCODER_REPO="${ZEROCODER_REPO:-git@github.com:your-org/zerocoder.git}"
DAEMON_DIR="${HOME}/zerocoder-daemon"
NODE_VERSION="${NODE_VERSION:-24}"
DAEMON_PORT="${DAEMON_PORT:-9999}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# =============================================================================
# Step 1: Install Node.js via nvm
# =============================================================================

install_nodejs() {
    log_info "Checking Node.js installation..."

    # Check if node exists and is the right version
    if command -v node &> /dev/null; then
        local current_version
        current_version=$(node --version | sed 's/v//' | cut -d. -f1)
        if [ "$current_version" -ge 20 ]; then
            log_info "Node.js v$(node --version) already installed"
            return 0
        fi
    fi

    log_info "Installing Node.js ${NODE_VERSION}..."

    # Check if nvm is installed
    if [ ! -d "$HOME/.nvm" ]; then
        log_info "Installing nvm..."
        curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.3/install.sh | bash
    fi

    # Load nvm
    export NVM_DIR="$HOME/.nvm"
    # shellcheck source=/dev/null
    [ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"

    # Install Node.js
    nvm install "$NODE_VERSION"
    nvm use "$NODE_VERSION"
    nvm alias default "$NODE_VERSION"

    log_info "Node.js v$(node --version) installed"
}

# =============================================================================
# Step 2: Install Rust and beads CLI
# =============================================================================

install_beads() {
    log_info "Checking beads CLI installation..."

    if command -v bd &> /dev/null; then
        log_info "beads CLI already installed"
        # Update to latest
        if [ -d "$HOME/.beads-cli" ]; then
            log_info "Updating beads CLI..."
            cd "$HOME/.beads-cli" && git pull && cargo build --release
        fi
        return 0
    fi

    # Check if Rust is installed
    if ! command -v cargo &> /dev/null; then
        log_info "Installing Rust..."
        curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
        # shellcheck source=/dev/null
        source "$HOME/.cargo/env"
    fi

    log_info "Installing beads CLI..."

    # Clone and build beads
    if [ -d "$HOME/.beads-cli" ]; then
        cd "$HOME/.beads-cli" && git pull
    else
        git clone https://github.com/steveyegge/beads.git "$HOME/.beads-cli"
    fi

    cd "$HOME/.beads-cli" && cargo build --release

    # Add to PATH
    if ! grep -q '.beads-cli' "$HOME/.bashrc" 2>/dev/null; then
        echo 'export PATH="$HOME/.beads-cli/target/release:$PATH"' >> "$HOME/.bashrc"
    fi

    export PATH="$HOME/.beads-cli/target/release:$PATH"

    log_info "beads CLI installed"
}

# =============================================================================
# Step 3: Install Claude Code CLI
# =============================================================================

install_claude_code() {
    log_info "Checking Claude Code installation..."

    if command -v claude &> /dev/null; then
        log_info "Claude Code already installed"
        return 0
    fi

    log_info "Installing Claude Code..."
    curl -fsSL https://claude.ai/install.sh | bash

    log_info "Claude Code installed"
}

# =============================================================================
# Step 4: Clone/update ZeroCoder and build daemon
# =============================================================================

install_daemon() {
    log_info "Setting up ZeroCoder daemon..."

    # Ensure we're using the right Node.js
    export NVM_DIR="$HOME/.nvm"
    # shellcheck source=/dev/null
    [ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"

    # Clone or update repo
    if [ -d "$DAEMON_DIR" ]; then
        log_info "Updating ZeroCoder..."
        cd "$DAEMON_DIR" && git fetch --all && git reset --hard origin/main
    else
        log_info "Cloning ZeroCoder..."
        git clone "$ZEROCODER_REPO" "$DAEMON_DIR"
    fi

    cd "$DAEMON_DIR"

    # Install pnpm if not available
    if ! command -v pnpm &> /dev/null; then
        log_info "Installing pnpm..."
        npm install -g pnpm
    fi

    # Install dependencies and build
    log_info "Installing dependencies..."
    pnpm install

    log_info "Building daemon..."
    pnpm --filter @zerocoder/daemon build

    log_info "Daemon built successfully"
}

# =============================================================================
# Step 5: Start the daemon
# =============================================================================

start_daemon() {
    log_info "Starting daemon on port $DAEMON_PORT..."

    cd "$DAEMON_DIR/packages/daemon"

    # Check if daemon is already running
    if pgrep -f "node.*daemon.*index.js" > /dev/null; then
        log_warn "Daemon appears to be already running"
        return 0
    fi

    # Ensure we're using the right Node.js
    export NVM_DIR="$HOME/.nvm"
    # shellcheck source=/dev/null
    [ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"

    # Start daemon in background
    export DAEMON_PORT
    nohup node dist/index.js > "$HOME/zerocoder-daemon.log" 2>&1 &
    local daemon_pid=$!

    echo "$daemon_pid" > "$HOME/.zerocoder-daemon.pid"

    # Wait a moment and check if it started
    sleep 2

    if ps -p "$daemon_pid" > /dev/null; then
        log_info "Daemon started with PID $daemon_pid"
        log_info "Logs: $HOME/zerocoder-daemon.log"
        log_info "Listening on port $DAEMON_PORT"
    else
        log_error "Daemon failed to start. Check logs: $HOME/zerocoder-daemon.log"
        return 1
    fi
}

# =============================================================================
# Helper: Stop daemon
# =============================================================================

stop_daemon() {
    log_info "Stopping daemon..."

    if [ -f "$HOME/.zerocoder-daemon.pid" ]; then
        local pid
        pid=$(cat "$HOME/.zerocoder-daemon.pid")
        if ps -p "$pid" > /dev/null 2>&1; then
            kill "$pid"
            log_info "Daemon stopped (PID $pid)"
        fi
        rm -f "$HOME/.zerocoder-daemon.pid"
    fi

    # Also kill any orphaned processes
    pkill -f "node.*daemon.*index.js" 2>/dev/null || true
}

# =============================================================================
# Main
# =============================================================================

main() {
    local action="${1:-install}"

    case "$action" in
        install)
            log_info "=== ZeroCoder Daemon Installation ==="
            install_nodejs
            install_beads
            install_claude_code
            install_daemon
            start_daemon
            log_info "=== Installation complete ==="
            ;;
        start)
            start_daemon
            ;;
        stop)
            stop_daemon
            ;;
        restart)
            stop_daemon
            sleep 2
            start_daemon
            ;;
        update)
            stop_daemon
            install_daemon
            start_daemon
            ;;
        *)
            echo "Usage: $0 {install|start|stop|restart|update}"
            exit 1
            ;;
    esac
}

main "$@"
