#!/bin/bash
# Cleanup script for migrating to standalone container architecture
# Removes worktree-related state and resets container tracking

set -e

echo "=== ZeroCoder Standalone Migration Cleanup ==="

# 1. Remove worktrees directory
if [ -d ~/.zerocoder/worktrees ]; then
    echo "Removing ~/.zerocoder/worktrees/ (~3.8GB)..."
    rm -rf ~/.zerocoder/worktrees
    echo "  Done."
else
    echo "No worktrees directory found (already clean)."
fi

# 2. Remove bare repos directory
if [ -d ~/.zerocoder/repos ]; then
    echo "Removing ~/.zerocoder/repos/..."
    rm -rf ~/.zerocoder/repos
    echo "  Done."
else
    echo "No repos directory found (already clean)."
fi

# 3. Remove stopped zerocoder containers
echo "Removing stopped zerocoder containers..."
containers=$(docker ps -a --filter "name=zerocoder-" --format "{{.Names}}" 2>/dev/null || true)
if [ -n "$containers" ]; then
    echo "$containers" | xargs docker rm 2>/dev/null || true
    echo "  Done."
else
    echo "  No containers to remove."
fi

# 4. Reset SQLite registry
if [ -f ~/.zerocoder/registry.db ]; then
    echo "Resetting registry database..."
    sqlite3 ~/.zerocoder/registry.db "DELETE FROM worktrees;" 2>/dev/null || echo "  (worktrees table doesn't exist)"
    sqlite3 ~/.zerocoder/registry.db "DELETE FROM containers;" 2>/dev/null || echo "  (containers table doesn't exist)"
    sqlite3 ~/.zerocoder/registry.db "DELETE FROM feature_cache;" 2>/dev/null || echo "  (feature_cache table doesn't exist)"
    sqlite3 ~/.zerocoder/registry.db "DELETE FROM feature_stats_cache;" 2>/dev/null || echo "  (feature_stats_cache table doesn't exist)"
    echo "  Done."
else
    echo "No registry.db found (will be created on first run)."
fi

# 5. Remove old backup
if [ -f ~/.zerocoder/registry.db.bak ]; then
    echo "Removing old registry backup..."
    rm -f ~/.zerocoder/registry.db.bak
    echo "  Done."
fi

# 6. Clean project state files
echo "Cleaning project state files..."
for project_dir in ~/.zerocoder/projects/*/; do
    if [ -d "$project_dir" ]; then
        rm -f "$project_dir/.agent_state.json" 2>/dev/null || true
        rm -f "$project_dir"/.agent_started.* 2>/dev/null || true
        rm -f "$project_dir/.beads/daemon.lock" "$project_dir/.beads/daemon.pid" 2>/dev/null || true
    fi
done
echo "  Done."

echo ""
echo "=== Cleanup Complete ==="
echo ""
echo "Removed:"
echo "  - worktrees/ directory"
echo "  - repos/ directory (bare repos)"
echo "  - Stopped zerocoder containers"
echo "  - Registry state (worktrees, containers, caches)"
echo "  - Project state files (.agent_state.json, locks)"
echo ""
echo "Preserved:"
echo "  - projects/ directory (source code)"
echo "  - beads databases (.beads/beads.db)"
echo "  - Docker image (zerocoder-project:latest)"
echo ""
echo "You can now start fresh with: ./start-app.sh"
