"""
Backend Services
================

Business logic and container management services.
"""

from .container_manager import ContainerManager
from .beads_manager import BeadsManager, get_beads_manager, get_beads_sync_manager
from .local_project_manager import LocalProjectManager, get_local_project_manager

# Backwards compatibility alias
BeadsSyncManager = BeadsManager

__all__ = [
    "ContainerManager",
    "BeadsManager",
    "BeadsSyncManager",  # Backwards compatibility
    "get_beads_manager",
    "get_beads_sync_manager",  # Backwards compatibility
    "LocalProjectManager",
    "get_local_project_manager",
]
