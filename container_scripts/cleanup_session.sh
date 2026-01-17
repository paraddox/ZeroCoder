#!/bin/bash
# =============================================================================
# Session Cleanup Script
# =============================================================================
# Runs after each agent session ends to clean up git state.
#
# Actions:
#   1. Abort stuck git operations (rebase, merge, cherry-pick)
#   2. Switch to main branch
#   3. Discard uncommitted changes (reset + clean)
#   4. Delete local feature branches (keep main and beads-sync)
#   5. Pull latest from main
#   6. Sync beads state

set -o pipefail

PROJECT_DIR="/project"

log() {
    echo "[$(date -Iseconds)] [cleanup] $*" | tee -a /var/log/agent.log
}

log "Starting session cleanup"
cd "$PROJECT_DIR" || exit 1

# 1. Abort stuck git operations
git rebase --abort 2>/dev/null || true
git merge --abort 2>/dev/null || true
git cherry-pick --abort 2>/dev/null || true

# 2. Switch to main branch, discard changes
log "Resetting to main branch..."
git checkout main 2>&1 || git reset --hard HEAD
git reset --hard HEAD 2>&1 || true
git clean -fd 2>&1 || true

# 3. Delete feature branches (keep main and beads-sync)
log "Cleaning up local branches..."
for branch in $(git branch --list | grep -v '^\*' | grep -v 'main' | grep -v 'beads-sync'); do
    branch=$(echo "$branch" | tr -d ' ')
    if [ -n "$branch" ]; then
        git branch -D "$branch" 2>&1 || true
    fi
done

# 4. Pull latest from main
log "Pulling latest..."
git fetch origin 2>&1 || true
git pull --rebase origin main 2>&1 || git reset --hard origin/main 2>&1 || true

# 5. Sync beads state (use --no-daemon to avoid conflicts)
if [ -d "$PROJECT_DIR/.beads" ]; then
    log "Syncing beads..."
    bd --no-daemon sync 2>&1 || true
fi

log "Session cleanup complete"
exit 0
