#!/bin/bash
# =============================================================================
# Repository Setup Script
# =============================================================================
# Runs after repo clone/pull in container entrypoint.
# Handles beads sync via host API (beads_client) instead of local bd.
#
# For init containers: Skip beads sync (agent creates beads from scratch)
# For coding containers: Sync beads state via host API
#
# Environment variables:
#   CONTAINER_TYPE: "init" or "coding" (default: coding)
#   HOST_API_URL: Host API URL for beads operations
#   PROJECT_NAME: Project name for beads operations

set -o pipefail

CONTAINER_TYPE="${CONTAINER_TYPE:-coding}"
PROJECT_DIR="/project"
BEADS_DIR="$PROJECT_DIR/.beads"

log() {
    echo "[$(date -Iseconds)] [setup_repo] $*" | tee -a /var/log/agent.log
}

log "Starting repository setup (type: $CONTAINER_TYPE)"
cd "$PROJECT_DIR" || exit 1

# Kill any stale daemon processes and remove lock files
if [ -f "$BEADS_DIR/daemon.pid" ]; then
    DAEMON_PID=$(cat "$BEADS_DIR/daemon.pid" 2>/dev/null)
    if [ -n "$DAEMON_PID" ] && kill -0 "$DAEMON_PID" 2>/dev/null; then
        log "Stopping stale beads daemon (PID: $DAEMON_PID)"
        kill "$DAEMON_PID" 2>/dev/null || true
        sleep 1
    fi
    rm -f "$BEADS_DIR/daemon.pid" "$BEADS_DIR/daemon.lock"
fi

# Skip beads sync for init containers - agent will create beads from scratch
if [ "$CONTAINER_TYPE" = "init" ]; then
    log "Init container - skipping beads sync"
    exit 0
fi

# Coding containers: Sync beads state via host API
if [ -d "$BEADS_DIR" ]; then
    # Check if beads_client is available and environment is set
    if command -v beads_client &> /dev/null && [ -n "$HOST_API_URL" ] && [ -n "$PROJECT_NAME" ]; then
        log "Syncing beads state via host API..."
        beads_client sync 2>&1 || log "WARNING: beads_client sync failed (host API may not be ready yet)"
    else
        log "Skipping beads sync (beads_client not configured)"
    fi
fi

log "Repository setup complete"
exit 0
