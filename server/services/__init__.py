"""
Backend Services
================

Business logic and container management services.
"""

from .container_manager import ContainerManager
from .beads_sync_manager import BeadsSyncManager, get_beads_sync_manager
from .local_project_manager import LocalProjectManager, get_local_project_manager

__all__ = [
    "ContainerManager",
    "BeadsSyncManager",
    "get_beads_sync_manager",
    "LocalProjectManager",
    "get_local_project_manager",
]
