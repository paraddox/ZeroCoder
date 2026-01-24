#!/bin/bash
# =============================================================================
# Repository Setup Script
# =============================================================================
# Runs after repo clone in container entrypoint.
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

# Verify repo was cloned successfully (done by entrypoint)
if [ ! -e "$PROJECT_DIR/.git" ]; then
    log "ERROR: /project/.git not found - repository not cloned"
    exit 1
fi

cd "$PROJECT_DIR" || exit 1
log "Repository verified at $PROJECT_DIR"

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

# NOTE: Beads sync is now handled by the host API server (BeadsManager)
# Container-side sync was removed to avoid race conditions and divergent branches
# when multiple containers try to sync simultaneously. The atomic /claim endpoint
# handles coordination between containers.
log "Skipping container-side beads sync (handled by host)"

log "Repository setup complete"
exit 0
