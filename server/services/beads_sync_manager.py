"""
Beads Sync Manager (Backwards Compatibility Stub)
=================================================

This module is DEPRECATED. Import from beads_manager instead.

All functionality has been unified into BeadsManager in beads_manager.py.
This stub re-exports everything for backwards compatibility with existing code.
"""

# Re-export everything from the unified beads_manager module
from .beads_manager import (
    # Main class
    BeadsManager,
    BeadsManager as BeadsSyncManager,  # Backwards compatibility alias
    # Factory functions
    get_beads_manager,
    get_beads_sync_manager,
    get_beads_manager_sync,
    clear_beads_manager,
    clear_beads_manager as clear_beads_sync_manager,  # Backwards compatibility alias
    # Convenience functions
    get_cached_stats,
    get_cached_features,
    _tasks_to_features,
    # Initialization and polling
    initialize_all_projects,
    pull_all_beads_sync,
    start_beads_sync_poller,
    # Constants
    POLL_INTERVAL_IDLE,
    POLL_INTERVAL_ACTIVE,
    # Helper
    get_beads_sync_dir,
    # Internal (for tests)
    _managers,
    _managers as _sync_managers,  # Backwards compatibility alias
    _managers_lock,
    _managers_lock as _sync_managers_lock,  # Backwards compatibility alias
)

__all__ = [
    # Main class
    "BeadsManager",
    "BeadsSyncManager",
    # Factory functions
    "get_beads_manager",
    "get_beads_sync_manager",
    "get_beads_manager_sync",
    "clear_beads_manager",
    "clear_beads_sync_manager",
    # Convenience functions
    "get_cached_stats",
    "get_cached_features",
    "_tasks_to_features",
    # Initialization and polling
    "initialize_all_projects",
    "pull_all_beads_sync",
    "start_beads_sync_poller",
    # Constants
    "POLL_INTERVAL_IDLE",
    "POLL_INTERVAL_ACTIVE",
    # Helper
    "get_beads_sync_dir",
    # Internal (for tests)
    "_managers",
    "_sync_managers",
    "_managers_lock",
    "_sync_managers_lock",
]
