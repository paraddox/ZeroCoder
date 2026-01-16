"""
Project Registry Module
=======================

Cross-platform project registry for storing project name to git URL mappings.
Uses SQLite database stored at ~/.zerocoder/registry.db.

Local clones are stored at:
- ~/.zerocoder/projects/{name}/ - Full clone for wizard and edit mode
- ~/.zerocoder/beads-sync/{name}/ - beads-sync branch clone for task state
"""

import logging
import os
import re
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import Boolean, CheckConstraint, Column, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# Module logger
logger = logging.getLogger(__name__)


# =============================================================================
# Exceptions
# =============================================================================

class RegistryError(Exception):
    """Base registry exception."""
    pass


class RegistryNotFound(RegistryError):
    """Registry file doesn't exist."""
    pass


class RegistryCorrupted(RegistryError):
    """Registry database is corrupted."""
    pass


class RegistryPermissionDenied(RegistryError):
    """Can't read/write registry file."""
    pass


# =============================================================================
# SQLAlchemy Model
# =============================================================================

Base = declarative_base()


class Project(Base):
    """SQLAlchemy model for registered projects."""
    __tablename__ = "projects"

    name = Column(String(50), primary_key=True, index=True)
    git_url = Column(String, nullable=False)  # git@github.com:user/repo.git or https://...
    is_new = Column(Boolean, default=True)  # True until wizard completed
    target_container_count = Column(Integer, default=1)  # 1-10 parallel agents
    created_at = Column(DateTime, nullable=False)

    __table_args__ = (
        CheckConstraint(
            'target_container_count >= 1 AND target_container_count <= 10',
            name='valid_target_container_count'
        ),
    )

    @property
    def local_path(self) -> Path:
        """Get the local clone path for this project."""
        return get_projects_dir() / self.name

    @property
    def beads_sync_path(self) -> Path:
        """Get the beads-sync clone path for this project."""
        return get_beads_sync_dir() / self.name


class Container(Base):
    """SQLAlchemy model for container instances."""
    __tablename__ = "containers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_name = Column(String(50), ForeignKey("projects.name", ondelete="CASCADE"), nullable=False, index=True)
    container_number = Column(Integer, nullable=False)
    container_type = Column(String(20), default='coding')  # 'init' or 'coding'
    docker_container_id = Column(String(100), nullable=True)
    status = Column(String(20), default='created')  # 'created', 'running', 'stopping', 'stopped'
    current_feature = Column(String(50), nullable=True)  # beads-42
    created_at = Column(DateTime, nullable=False, default=datetime.now)

    __table_args__ = (
        UniqueConstraint('project_name', 'container_number', 'container_type', name='uq_container_identity'),
        CheckConstraint("container_type IN ('init', 'coding')", name='valid_container_type'),
        CheckConstraint("status IN ('created', 'running', 'stopping', 'stopped')", name='valid_container_status'),
    )


class FeatureCache(Base):
    """Cached feature data from container polling."""
    __tablename__ = "feature_cache"

    project_name = Column(
        String(50),
        ForeignKey("projects.name", ondelete="CASCADE"),
        primary_key=True,
        index=True
    )
    feature_id = Column(String(50), primary_key=True)
    priority = Column(Integer, default=999)
    category = Column(String(100), default="")
    name = Column(String(255), nullable=False)
    description = Column(Text, default="")
    steps_json = Column(Text, default="[]")  # JSON array of steps
    status = Column(String(20), nullable=False)  # open, in_progress, closed
    updated_at = Column(DateTime, nullable=False)

    __table_args__ = (
        CheckConstraint("status IN ('open', 'in_progress', 'closed')", name='valid_feature_status'),
    )


class FeatureStatsCache(Base):
    """Cached aggregate feature stats for quick access."""
    __tablename__ = "feature_stats_cache"

    project_name = Column(
        String(50),
        ForeignKey("projects.name", ondelete="CASCADE"),
        primary_key=True,
        index=True
    )
    pending_count = Column(Integer, default=0)
    in_progress_count = Column(Integer, default=0)
    done_count = Column(Integer, default=0)
    total_count = Column(Integer, default=0)
    percentage = Column(Float, default=0.0)
    last_polled_at = Column(DateTime, nullable=False)
    poll_error = Column(String(500), nullable=True)


# =============================================================================
# Database Connection
# =============================================================================

# Module-level singleton for database engine
_engine = None
_SessionLocal = None


def get_config_dir() -> Path:
    """
    Get the config directory.

    Uses ZEROCODER_DATA_DIR environment variable if set (for Docker),
    otherwise defaults to ~/.zerocoder/

    Returns:
        Path to config directory (created if it doesn't exist)
    """
    data_dir = os.getenv("ZEROCODER_DATA_DIR")
    if data_dir:
        config_dir = Path(data_dir) / "zerocoder"
    else:
        config_dir = Path.home() / ".zerocoder"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir


def get_projects_dir() -> Path:
    """
    Get the projects directory for local clones.

    Returns:
        Path to ~/.zerocoder/projects/ (created if it doesn't exist)
    """
    projects_dir = get_config_dir() / "projects"
    projects_dir.mkdir(parents=True, exist_ok=True)
    return projects_dir


def get_beads_sync_dir() -> Path:
    """
    Get the beads-sync directory for beads-sync branch clones.

    Returns:
        Path to ~/.zerocoder/beads-sync/ (created if it doesn't exist)
    """
    beads_sync_dir = get_config_dir() / "beads-sync"
    beads_sync_dir.mkdir(parents=True, exist_ok=True)
    return beads_sync_dir


def get_registry_path() -> Path:
    """Get the path to the registry database."""
    return get_config_dir() / "registry.db"


def _get_engine():
    """
    Get or create the database engine (singleton pattern).

    Returns:
        Tuple of (engine, SessionLocal)
    """
    global _engine, _SessionLocal

    if _engine is None:
        db_path = get_registry_path()
        db_url = f"sqlite:///{db_path.as_posix()}"
        _engine = create_engine(db_url, connect_args={"check_same_thread": False})
        Base.metadata.create_all(bind=_engine)
        _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_engine)
        logger.debug("Initialized registry database at: %s", db_path)

    return _engine, _SessionLocal


@contextmanager
def _get_session():
    """
    Context manager for database sessions with automatic commit/rollback.

    Yields:
        SQLAlchemy session
    """
    _, SessionLocal = _get_engine()
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# =============================================================================
# Project CRUD Functions
# =============================================================================

def register_project(name: str, git_url: str, is_new: bool = True) -> None:
    """
    Register a new project in the registry.

    Args:
        name: The project name (unique identifier).
        git_url: Git repository URL (https:// or git@).
        is_new: True if this is a new project needing wizard setup.

    Raises:
        ValueError: If project name is invalid or git_url is invalid.
        RegistryError: If a project with that name already exists.
    """
    # Validate name
    if not re.match(r'^[a-zA-Z0-9_-]{1,50}$', name):
        raise ValueError(
            "Invalid project name. Use only letters, numbers, hyphens, "
            "and underscores (1-50 chars)."
        )

    # Validate git URL
    if not (git_url.startswith('https://') or git_url.startswith('git@')):
        raise ValueError("Invalid git URL. Must start with https:// or git@")

    with _get_session() as session:
        existing = session.query(Project).filter(Project.name == name).first()
        if existing:
            logger.warning("Attempted to register duplicate project: %s", name)
            raise RegistryError(f"Project '{name}' already exists in registry")

        project = Project(
            name=name,
            git_url=git_url,
            is_new=is_new,
            target_container_count=1,
            created_at=datetime.now()
        )
        session.add(project)

    logger.info("Registered project '%s' with git URL: %s", name, git_url)


def unregister_project(name: str) -> bool:
    """
    Remove a project from the registry.

    Args:
        name: The project name to remove.

    Returns:
        True if removed, False if project wasn't found.
    """
    with _get_session() as session:
        project = session.query(Project).filter(Project.name == name).first()
        if not project:
            logger.debug("Attempted to unregister non-existent project: %s", name)
            return False

        session.delete(project)

    logger.info("Unregistered project: %s", name)
    return True


def get_project_path(name: str) -> Path | None:
    """
    Look up a project's local clone path by name.

    Args:
        name: The project name.

    Returns:
        The project local clone Path, or None if not found.
    """
    _, SessionLocal = _get_engine()
    session = SessionLocal()
    try:
        project = session.query(Project).filter(Project.name == name).first()
        if project is None:
            return None
        return get_projects_dir() / name
    finally:
        session.close()


def get_project_git_url(name: str) -> str | None:
    """
    Look up a project's git URL by name.

    Args:
        name: The project name.

    Returns:
        The project git URL, or None if not found.
    """
    _, SessionLocal = _get_engine()
    session = SessionLocal()
    try:
        project = session.query(Project).filter(Project.name == name).first()
        if project is None:
            return None
        return project.git_url
    finally:
        session.close()


def list_registered_projects() -> dict[str, dict[str, Any]]:
    """
    Get all registered projects.

    Returns:
        Dictionary mapping project names to their info dictionaries.
    """
    _, SessionLocal = _get_engine()
    session = SessionLocal()
    try:
        projects = session.query(Project).all()
        return {
            p.name: {
                "git_url": p.git_url,
                "is_new": p.is_new,
                "target_container_count": p.target_container_count,
                "local_path": (get_projects_dir() / p.name).as_posix(),
                "created_at": p.created_at.isoformat() if p.created_at else None
            }
            for p in projects
        }
    finally:
        session.close()


def get_project_info(name: str) -> dict[str, Any] | None:
    """
    Get full info about a project.

    Args:
        name: The project name.

    Returns:
        Project info dictionary, or None if not found.
    """
    _, SessionLocal = _get_engine()
    session = SessionLocal()
    try:
        project = session.query(Project).filter(Project.name == name).first()
        if project is None:
            return None
        return {
            "git_url": project.git_url,
            "is_new": project.is_new,
            "target_container_count": project.target_container_count,
            "local_path": (get_projects_dir() / project.name).as_posix(),
            "created_at": project.created_at.isoformat() if project.created_at else None
        }
    finally:
        session.close()


def update_project_git_url(name: str, new_git_url: str) -> bool:
    """
    Update a project's git URL.

    Args:
        name: The project name.
        new_git_url: The new git URL.

    Returns:
        True if updated, False if project wasn't found.
    """
    if not (new_git_url.startswith('https://') or new_git_url.startswith('git@')):
        raise ValueError("Invalid git URL. Must start with https:// or git@")

    with _get_session() as session:
        project = session.query(Project).filter(Project.name == name).first()
        if not project:
            return False

        project.git_url = new_git_url

    return True


def mark_project_initialized(name: str) -> bool:
    """
    Mark a project as initialized (wizard completed).

    Args:
        name: The project name.

    Returns:
        True if updated, False if project wasn't found.
    """
    with _get_session() as session:
        project = session.query(Project).filter(Project.name == name).first()
        if not project:
            return False

        project.is_new = False

    return True


def update_target_container_count(name: str, count: int) -> bool:
    """
    Update a project's target container count.

    Args:
        name: The project name.
        count: The target container count (1-10).

    Returns:
        True if updated, False if project wasn't found.
    """
    if not 1 <= count <= 10:
        raise ValueError("Container count must be between 1 and 10")

    with _get_session() as session:
        project = session.query(Project).filter(Project.name == name).first()
        if not project:
            return False

        project.target_container_count = count

    return True


# =============================================================================
# Validation Functions
# =============================================================================

def validate_project_path(path: Path) -> tuple[bool, str]:
    """
    Validate that a project path is accessible and writable.

    Args:
        path: The path to validate.

    Returns:
        Tuple of (is_valid, error_message).
    """
    path = Path(path).resolve()

    # Check if path exists
    if not path.exists():
        return False, f"Path does not exist: {path}"

    # Check if it's a directory
    if not path.is_dir():
        return False, f"Path is not a directory: {path}"

    # Check read permissions
    if not os.access(path, os.R_OK):
        return False, f"No read permission: {path}"

    # Check write permissions
    if not os.access(path, os.W_OK):
        return False, f"No write permission: {path}"

    return True, ""


def validate_git_url(git_url: str) -> tuple[bool, str]:
    """
    Validate that a git URL is properly formatted.

    Args:
        git_url: The git URL to validate.

    Returns:
        Tuple of (is_valid, error_message).
    """
    if not git_url:
        return False, "Git URL cannot be empty"

    if not (git_url.startswith('https://') or git_url.startswith('git@')):
        return False, "Git URL must start with https:// or git@"

    return True, ""


def cleanup_stale_projects() -> list[str]:
    """
    Remove projects from registry whose local clones no longer exist.

    Returns:
        List of removed project names.
    """
    removed = []

    with _get_session() as session:
        projects = session.query(Project).all()
        for project in projects:
            local_path = get_projects_dir() / project.name
            if not local_path.exists():
                session.delete(project)
                removed.append(project.name)

    if removed:
        logger.info("Cleaned up stale projects: %s", removed)

    return removed


def list_valid_projects() -> list[dict[str, Any]]:
    """
    List all projects that have valid, accessible local clones.

    Returns:
        List of project info dicts with additional 'name' field.
    """
    _, SessionLocal = _get_engine()
    session = SessionLocal()
    try:
        projects = session.query(Project).all()
        valid = []
        for p in projects:
            local_path = get_projects_dir() / p.name
            is_valid, _ = validate_project_path(local_path)
            if is_valid:
                valid.append({
                    "name": p.name,
                    "git_url": p.git_url,
                    "is_new": p.is_new,
                    "target_container_count": p.target_container_count,
                    "local_path": local_path.as_posix(),
                    "created_at": p.created_at.isoformat() if p.created_at else None
                })
        return valid
    finally:
        session.close()


# =============================================================================
# Container CRUD Functions
# =============================================================================

def create_container(project_name: str, container_number: int, container_type: str = 'coding') -> int:
    """
    Create or get an existing container record.

    If a container with the same (project_name, container_number, container_type)
    already exists, returns its ID and resets its status to 'created'.

    Args:
        project_name: The project this container belongs to.
        container_number: The container number (1-10).
        container_type: 'init' or 'coding'.

    Returns:
        The container's ID.
    """
    with _get_session() as session:
        # Check if container already exists
        existing = session.query(Container).filter(
            Container.project_name == project_name,
            Container.container_number == container_number,
            Container.container_type == container_type
        ).first()

        if existing:
            # Reset status for reuse
            existing.status = 'created'
            existing.current_feature = None
            session.flush()
            return existing.id

        # Create new container
        container = Container(
            project_name=project_name,
            container_number=container_number,
            container_type=container_type,
            status='created',
            created_at=datetime.now()
        )
        session.add(container)
        try:
            session.flush()
            return container.id
        except IntegrityError:
            # Race condition: another thread created the container between our check and insert
            session.rollback()
            existing = session.query(Container).filter(
                Container.project_name == project_name,
                Container.container_number == container_number,
                Container.container_type == container_type
            ).first()
            if existing:
                existing.status = 'created'
                existing.current_feature = None
                session.flush()
                return existing.id
            raise  # Re-raise if still not found (shouldn't happen)


def get_container(project_name: str, container_number: int, container_type: str = 'coding') -> dict[str, Any] | None:
    """
    Get a container record by project, number, and type.

    Returns:
        Container info dict, or None if not found.
    """
    _, SessionLocal = _get_engine()
    session = SessionLocal()
    try:
        container = session.query(Container).filter(
            Container.project_name == project_name,
            Container.container_number == container_number,
            Container.container_type == container_type
        ).first()

        if not container:
            return None

        return {
            "id": container.id,
            "project_name": container.project_name,
            "container_number": container.container_number,
            "container_type": container.container_type,
            "docker_container_id": container.docker_container_id,
            "status": container.status,
            "current_feature": container.current_feature,
            "created_at": container.created_at.isoformat() if container.created_at else None
        }
    finally:
        session.close()


def list_containers(status_filter: list[str] | None = None) -> list[Container]:
    """
    List all containers across all projects.

    Args:
        status_filter: Optional list of statuses to filter by (e.g., ['running', 'stopping']).

    Returns:
        List of Container model objects.
    """
    _, SessionLocal = _get_engine()
    session = SessionLocal()
    try:
        query = session.query(Container)
        if status_filter:
            query = query.filter(Container.status.in_(status_filter))
        return query.all()
    finally:
        session.close()


def list_project_containers(project_name: str, container_type: str | None = None) -> list[dict[str, Any]]:
    """
    List all containers for a project.

    Args:
        project_name: The project name.
        container_type: Filter by type ('init', 'coding'), or None for all.

    Returns:
        List of container info dicts.
    """
    _, SessionLocal = _get_engine()
    session = SessionLocal()
    try:
        query = session.query(Container).filter(Container.project_name == project_name)
        if container_type:
            query = query.filter(Container.container_type == container_type)

        containers = query.order_by(Container.container_number).all()
        return [
            {
                "id": c.id,
                "project_name": c.project_name,
                "container_number": c.container_number,
                "container_type": c.container_type,
                "docker_container_id": c.docker_container_id,
                "status": c.status,
                "current_feature": c.current_feature,
                "created_at": c.created_at.isoformat() if c.created_at else None
            }
            for c in containers
        ]
    finally:
        session.close()


def update_container_status(
    project_name: str,
    container_number: int,
    container_type: str = 'coding',
    status: str | None = None,
    docker_container_id: str | None = None,
    current_feature: str | None = None
) -> bool:
    """
    Update a container's status and/or docker ID.

    Returns:
        True if updated, False if not found.
    """
    with _get_session() as session:
        container = session.query(Container).filter(
            Container.project_name == project_name,
            Container.container_number == container_number,
            Container.container_type == container_type
        ).first()

        if not container:
            return False

        if status is not None:
            container.status = status
        if docker_container_id is not None:
            container.docker_container_id = docker_container_id
        if current_feature is not None:
            container.current_feature = current_feature

    return True


def delete_container(project_name: str, container_number: int, container_type: str = 'coding') -> bool:
    """
    Delete a container record.

    Returns:
        True if deleted, False if not found.
    """
    with _get_session() as session:
        container = session.query(Container).filter(
            Container.project_name == project_name,
            Container.container_number == container_number,
            Container.container_type == container_type
        ).first()

        if not container:
            return False

        session.delete(container)
    return True


def delete_all_project_containers(project_name: str) -> int:
    """
    Delete all container records for a project.

    Returns:
        Number of containers deleted.
    """
    with _get_session() as session:
        deleted = session.query(Container).filter(Container.project_name == project_name).delete()
    return deleted
