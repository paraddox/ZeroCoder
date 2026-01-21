#!/bin/bash
# =============================================================================
# E2B Sandbox Setup Script
# =============================================================================
# Runs at sandbox startup to initialize the environment.
#
# Tasks:
# 1. Decode SSH key from environment variable
# 2. Clone repository from GIT_REMOTE_URL
# 3. Set up working directory
#
# Environment variables (required):
#   GIT_REMOTE_URL - Git SSH URL to clone
#   SSH_PRIVATE_KEY_BASE64 - Base64-encoded SSH private key
#
# Environment variables (optional):
#   HOST_API_URL - Host API URL for beads operations
#   PROJECT_NAME - Project name
#   CONTAINER_NUMBER - Container/sandbox number (default: 1)

set -e

PROJECT_DIR="/project"
LOG_FILE="/tmp/sandbox_setup.log"

log() {
    echo "[$(date -Iseconds)] [setup] $*" | tee -a "$LOG_FILE"
}

log "Starting E2B sandbox setup..."

# =============================================================================
# SSH Key Setup
# =============================================================================
if [ -n "$SSH_PRIVATE_KEY_BASE64" ]; then
    log "Decoding SSH key from environment..."
    echo "$SSH_PRIVATE_KEY_BASE64" | base64 -d > /root/.ssh/id_ed25519
    chmod 600 /root/.ssh/id_ed25519
    log "SSH key installed"
else
    log "WARNING: No SSH_PRIVATE_KEY_BASE64 provided - git clone may fail for private repos"
fi

# =============================================================================
# Repository Clone
# =============================================================================
if [ -z "$GIT_REMOTE_URL" ]; then
    log "ERROR: GIT_REMOTE_URL not set"
    exit 1
fi

log "Cloning repository: $GIT_REMOTE_URL"

if [ -d "$PROJECT_DIR/.git" ]; then
    log "Project already exists, pulling latest..."
    cd "$PROJECT_DIR"
    git fetch origin
    # Try to reset to default branch, handle empty repos
    if git rev-parse origin/main >/dev/null 2>&1; then
        git reset --hard origin/main
    elif git rev-parse origin/master >/dev/null 2>&1; then
        git reset --hard origin/master
    else
        log "Repository appears to be empty (no main/master branch)"
    fi
else
    log "Cloning fresh copy..."
    # Clone into temp dir first, then move (can't clone into non-empty dir)
    rm -rf /tmp/project-clone

    # Clone without specifying branch (works for empty repos)
    if git clone "$GIT_REMOTE_URL" /tmp/project-clone 2>&1; then
        # Move all files including hidden ones
        mv /tmp/project-clone/* /tmp/project-clone/.[!.]* "$PROJECT_DIR/" 2>/dev/null || true
        rm -rf /tmp/project-clone
    else
        # Empty repo - initialize locally and add remote
        log "Repository is empty, initializing fresh..."
        cd "$PROJECT_DIR"
        git init
        git remote add origin "$GIT_REMOTE_URL"
        git checkout -b main
    fi
fi

if [ ! -e "$PROJECT_DIR/.git" ]; then
    log "ERROR: Git clone failed - $PROJECT_DIR/.git not found"
    exit 1
fi

log "Repository cloned successfully"

# =============================================================================
# Beads Cleanup
# =============================================================================
cd "$PROJECT_DIR"

# Clean up stale beads daemon lock files
if [ -f "$PROJECT_DIR/.beads/daemon.lock" ]; then
    rm -f "$PROJECT_DIR/.beads/daemon.lock"
    log "Removed stale beads daemon.lock"
fi

if [ -f "$PROJECT_DIR/.beads/daemon.pid" ]; then
    rm -f "$PROJECT_DIR/.beads/daemon.pid"
    log "Removed stale beads daemon.pid"
fi

# =============================================================================
# Git Configuration
# =============================================================================
# Mark project directory as safe for git operations
git config --global --add safe.directory "$PROJECT_DIR"

log "Sandbox setup complete - ready for agent"
