"""
Feature Status Poller
=====================

Background service that polls running containers for feature status
and caches results in SQLite.
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Dict

logger = logging.getLogger(__name__)

# Polling interval in seconds
POLL_INTERVAL = 30

# In-memory cache for quick access to stats
_stats_cache: Dict[str, dict] = {}


async def poll_container_features(container_name: str, project_name: str) -> dict | None:
    """
    Poll a single container for feature status via docker exec.

    Args:
        container_name: Docker container name
        project_name: Project name for cache storage

    Returns:
        Feature status dict or None on error
    """
    try:
        # Using create_subprocess_exec (not shell) - safe from injection
        result = await asyncio.create_subprocess_exec(
            "docker", "exec", "-u", "coder", container_name,
            "python", "/app/feature_status.py",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await asyncio.wait_for(
            result.communicate(),
            timeout=10  # 10 second timeout
        )

        if result.returncode != 0:
            logger.warning(f"Feature poll failed for {container_name}: {stderr.decode()}")
            return None

        data = json.loads(stdout.decode())

        if not data.get("success"):
            logger.warning(f"Feature poll error for {container_name}: {data.get('error')}")
            return None

        return data

    except asyncio.TimeoutError:
        logger.warning(f"Feature poll timeout for {container_name}")
        return None
    except json.JSONDecodeError as e:
        logger.warning(f"Invalid JSON from {container_name}: {e}")
        return None
    except Exception as e:
        logger.warning(f"Feature poll error for {container_name}: {e}")
        return None


def update_feature_cache(project_name: str, data: dict) -> None:
    """
    Update SQLite cache with polled feature data.

    Args:
        project_name: Project name
        data: Feature status data from container
    """
    from registry import _get_session, FeatureCache, FeatureStatsCache

    now = datetime.now()
    stats = data.get("stats", {})
    features = data.get("features", [])

    with _get_session() as session:
        # Update stats cache
        stats_record = session.query(FeatureStatsCache).filter(
            FeatureStatsCache.project_name == project_name
        ).first()

        if not stats_record:
            stats_record = FeatureStatsCache(
                project_name=project_name,
                last_polled_at=now
            )
            session.add(stats_record)

        stats_record.pending_count = stats.get("pending", 0)
        stats_record.in_progress_count = stats.get("in_progress", 0)
        stats_record.done_count = stats.get("done", 0)
        stats_record.total_count = stats.get("total", 0)
        stats_record.percentage = stats.get("percentage", 0.0)
        stats_record.last_polled_at = now
        stats_record.poll_error = None

        # Clear existing features for this project
        session.query(FeatureCache).filter(
            FeatureCache.project_name == project_name
        ).delete()

        # Insert new features
        for f in features:
            feature_record = FeatureCache(
                project_name=project_name,
                feature_id=f.get("id", ""),
                priority=f.get("priority", 999),
                category=f.get("category", ""),
                name=f.get("name", ""),
                description=f.get("description", ""),
                steps_json=json.dumps(f.get("steps", [])),
                status=f.get("status", "open"),
                updated_at=now,
            )
            session.add(feature_record)

    # Update in-memory cache
    _stats_cache[project_name] = {
        "stats": stats,
        "last_polled_at": now.isoformat(),
    }

    logger.debug(f"Updated cache for {project_name}: {stats}")


def get_cached_stats(project_name: str) -> dict:
    """
    Get cached stats for a project (fast, in-memory first).
    Falls back to SQLite if not in memory.
    """
    # Try in-memory cache first
    if project_name in _stats_cache:
        return _stats_cache[project_name]["stats"]

    # Fallback to SQLite
    from registry import _get_engine, FeatureStatsCache

    _, SessionLocal = _get_engine()
    session = SessionLocal()
    try:
        record = session.query(FeatureStatsCache).filter(
            FeatureStatsCache.project_name == project_name
        ).first()

        if record:
            stats = {
                "pending": record.pending_count,
                "in_progress": record.in_progress_count,
                "done": record.done_count,
                "total": record.total_count,
                "percentage": record.percentage,
            }
            # Populate in-memory cache
            _stats_cache[project_name] = {
                "stats": stats,
                "last_polled_at": record.last_polled_at.isoformat() if record.last_polled_at else None,
            }
            return stats
    finally:
        session.close()

    return {"pending": 0, "in_progress": 0, "done": 0, "total": 0, "percentage": 0.0}


def get_cached_features(project_name: str) -> list[dict]:
    """
    Get cached features for a project from SQLite.
    """
    from registry import _get_engine, FeatureCache

    _, SessionLocal = _get_engine()
    session = SessionLocal()
    try:
        records = session.query(FeatureCache).filter(
            FeatureCache.project_name == project_name
        ).order_by(FeatureCache.priority).all()

        features = []
        for r in records:
            features.append({
                "id": r.feature_id,
                "priority": r.priority,
                "category": r.category,
                "name": r.name,
                "description": r.description,
                "steps": json.loads(r.steps_json) if r.steps_json else [],
                "passes": r.status == "closed",
                "in_progress": r.status == "in_progress",
            })
        return features
    finally:
        session.close()


def clear_cache(project_name: str) -> None:
    """Clear cached data for a project."""
    # Clear in-memory cache
    if project_name in _stats_cache:
        del _stats_cache[project_name]

    # Clear SQLite cache
    from registry import _get_session, FeatureCache, FeatureStatsCache

    with _get_session() as session:
        session.query(FeatureCache).filter(
            FeatureCache.project_name == project_name
        ).delete()
        session.query(FeatureStatsCache).filter(
            FeatureStatsCache.project_name == project_name
        ).delete()


async def poll_all_running_containers() -> list[str]:
    """
    Poll all running zerocoder containers for feature status.

    Returns:
        List of project names that were polled
    """
    from .container_manager import _managers, _managers_lock

    polled = []

    with _managers_lock:
        # _managers is now dict[str, dict[int, ContainerManager]]
        all_managers = []
        for project_name, container_managers in _managers.items():
            for container_num, manager in container_managers.items():
                all_managers.append((project_name, manager))

    for project_name, manager in all_managers:
        # Only poll running containers
        if manager.status != "running":
            continue

        data = await poll_container_features(manager.container_name, project_name)

        if data:
            update_feature_cache(project_name, data)
            if project_name not in polled:
                polled.append(project_name)

    return polled


async def start_feature_poller() -> None:
    """
    Start the background feature polling task.
    Polls every POLL_INTERVAL seconds.
    """
    logger.info(f"Starting feature status poller (interval: {POLL_INTERVAL}s)")

    while True:
        try:
            await asyncio.sleep(POLL_INTERVAL)
            polled = await poll_all_running_containers()
            if polled:
                logger.debug(f"Polled features for: {polled}")
        except asyncio.CancelledError:
            logger.info("Feature poller stopped")
            break
        except Exception as e:
            logger.exception(f"Feature poller error: {e}")
