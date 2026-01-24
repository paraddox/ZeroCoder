#!/bin/bash
# Setup script for remote machines
# Creates workspace, clones repo, and installs dependencies

set -e

PROJECT_NAME="${1:?Usage: setup_remote.sh <project_name> <git_url>}"
GIT_URL="${2:?Usage: setup_remote.sh <project_name> <git_url>}"
WORKSPACE="$HOME/zerocoder/$PROJECT_NAME"

echo "[setup] Setting up workspace: $WORKSPACE"

# Create workspace directory
mkdir -p "$WORKSPACE"

# Clone or update repo
if [ -d "$WORKSPACE/.git" ]; then
    echo "[setup] Updating existing repo..."
    cd "$WORKSPACE"
    git fetch --all
    git reset --hard origin/main 2>/dev/null || git reset --hard origin/master
else
    echo "[setup] Cloning repo..."
    rm -rf "$WORKSPACE"
    git clone "$GIT_URL" "$WORKSPACE"
fi

cd "$WORKSPACE"

# Check for beads CLI
if ! command -v bd &>/dev/null; then
    echo "[setup] Installing beads CLI..."
    pip install beads-cli 2>/dev/null || pip3 install beads-cli 2>/dev/null || true
fi

echo "[setup] Workspace ready: $WORKSPACE"
