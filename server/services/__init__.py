"""
Backend Services
================

Business logic and E2B sandbox management services.
"""

from .e2b_sandbox_manager import E2BSandboxManager
from .beads_manager import BeadsManager, get_beads_manager, get_beads_sync_manager
from .local_project_manager import LocalProjectManager, get_local_project_manager

# Backwards compatibility aliases
BeadsSyncManager = BeadsManager
ContainerManager = E2BSandboxManager  # Alias for backwards compatibility

__all__ = [
    "E2BSandboxManager",
    "ContainerManager",  # Backwards compatibility alias
    "BeadsManager",
    "BeadsSyncManager",  # Backwards compatibility
    "get_beads_manager",
    "get_beads_sync_manager",  # Backwards compatibility
    "LocalProjectManager",
    "get_local_project_manager",
]
