#!/bin/bash
# =============================================================================
# Repository Setup Script
# =============================================================================
# Runs after repo clone/pull in container entrypoint to initialize beads.
#
# For init containers: Skip bd init (agent creates beads from scratch)
# For coding containers: Run bd init if .beads/ missing, then doctor and sync
#
# Environment variables:
#   CONTAINER_TYPE: "init" or "coding" (default: coding)

set -o pipefail

CONTAINER_TYPE="${CONTAINER_TYPE:-coding}"
PROJECT_DIR="/project"
BEADS_DIR="$PROJECT_DIR/.beads"

log() {
    echo "[$(date -Iseconds)] [setup_repo] $*" | tee -a /var/log/agent.log
}

log "Starting repository setup (type: $CONTAINER_TYPE)"
cd "$PROJECT_DIR" || exit 1

# Kill any stale daemon and remove lock files
if [ -f "$BEADS_DIR/daemon.pid" ]; then
    DAEMON_PID=$(cat "$BEADS_DIR/daemon.pid" 2>/dev/null)
    if [ -n "$DAEMON_PID" ] && kill -0 "$DAEMON_PID" 2>/dev/null; then
        log "Stopping stale beads daemon (PID: $DAEMON_PID)"
        kill "$DAEMON_PID" 2>/dev/null || true
        sleep 1
    fi
    rm -f "$BEADS_DIR/daemon.pid" "$BEADS_DIR/daemon.lock"
fi

# Skip bd init for init containers - agent will create beads from scratch
if [ "$CONTAINER_TYPE" = "init" ]; then
    log "Init container - skipping beads initialization"
    # Still run doctor if .beads/ exists (e.g., recovery scenario)
    if [ -d "$BEADS_DIR" ]; then
        bd --no-daemon doctor --fix --yes 2>&1 || true
    fi
    exit 0
fi

# Coding containers: Initialize beads if missing
if [ ! -d "$BEADS_DIR" ]; then
    log "Initializing beads with --branch beads-sync..."
    if ! bd --no-daemon init --branch beads-sync --prefix feat 2>&1; then
        log "WARNING: bd init failed (may already be initialized)"
    fi
fi

# Fix beads configuration and sync
if [ -d "$BEADS_DIR" ]; then
    log "Running bd doctor --fix..."
    bd --no-daemon doctor --fix --yes 2>&1 || log "WARNING: bd doctor failed"

    # Only sync if no other sync is in progress (agent may be syncing)
    if [ ! -f "$BEADS_DIR/.sync.lock" ]; then
        log "Syncing beads state..."
        bd --no-daemon sync 2>&1 || log "WARNING: bd sync failed"
    else
        log "Skipping sync (another sync in progress, agent will handle it)"
    fi
fi

log "Repository setup complete"
exit 0
