"""
Progress Tracking Utilities
===========================

Functions for tracking and displaying progress of the autonomous coding agent.
Uses live bd commands via BeadsManager for feature data.
"""

import json
import os
import urllib.request
from datetime import datetime
from pathlib import Path

WEBHOOK_URL = os.environ.get("PROGRESS_N8N_WEBHOOK_URL")
PROGRESS_CACHE_FILE = ".progress_cache"


def has_features(project_dir: Path, project_name: str | None = None) -> bool:
    """
    Check if the project has features in beads using live bd commands.

    This is used to determine if the initializer agent needs to run.

    Returns True if beads has issues.
    Returns False if no features exist (initializer needs to run).
    """
    if project_name:
        try:
            from server.services.beads_manager import get_cached_stats

            stats = get_cached_stats(project_name)
            return stats.get("total", 0) > 0
        except ImportError:
            pass  # Server modules not available

    # Fallback: check if .beads directory exists
    return (project_dir / ".beads" / "beads.db").exists()


def has_open_features(project_dir: Path, project_name: str | None = None) -> bool:
    """
    Check for open/in_progress features using live bd commands.

    This is used to determine if the overseer agent should run.
    Returns True if there are pending or in_progress features.
    Returns False if all features are closed (overseer should run).

    Args:
        project_dir: Directory containing the project (unused but kept for API compatibility)
        project_name: Optional project name for bd command lookup
    """
    if project_name:
        try:
            from server.services.beads_manager import get_cached_stats

            stats = get_cached_stats(project_name)
            return stats.get("pending", 0) + stats.get("in_progress", 0) > 0
        except ImportError:
            pass  # Server modules not available

    # Fallback: assume features exist (safer)
    return True


def count_passing_tests(project_dir: Path, project_name: str | None = None) -> tuple[int, int, int]:
    """
    Count passing, in_progress, and total tests using live bd commands.

    Args:
        project_dir: Directory containing the project (unused but kept for API compatibility)
        project_name: Optional project name for bd command lookup

    Returns:
        (passing_count, in_progress_count, total_count)
    """
    if project_name:
        try:
            from server.services.beads_manager import get_cached_stats

            stats = get_cached_stats(project_name)
            if stats.get("total", 0) > 0:
                return (
                    stats.get("done", 0),
                    stats.get("in_progress", 0),
                    stats.get("total", 0),
                )
        except ImportError:
            pass  # Server modules not available

    return 0, 0, 0


def get_all_passing_features(project_dir: Path, project_name: str | None = None) -> list[dict]:
    """
    Get all passing features using live bd commands.

    Args:
        project_dir: Directory containing the project (unused but kept for API compatibility)
        project_name: Optional project name for bd command lookup

    Returns:
        List of dicts with id, category, name for each passing feature
    """
    if project_name:
        try:
            from server.services.beads_manager import get_cached_features

            features = get_cached_features(project_name)
            return [
                {"id": f.get("id", ""), "category": f.get("category", ""), "name": f.get("name", "")}
                for f in features if f.get("passes") or f.get("status") == "closed"
            ]
        except ImportError:
            pass  # Server modules not available

    return []


def send_progress_webhook(passing: int, total: int, project_dir: Path, project_name: str | None = None) -> None:
    """Send webhook notification when progress increases."""
    if not WEBHOOK_URL:
        return  # Webhook not configured

    cache_file = project_dir / PROGRESS_CACHE_FILE
    previous = 0
    previous_passing_ids = set()

    # Read previous progress and passing feature IDs
    if cache_file.exists():
        try:
            cache_data = json.loads(cache_file.read_text())
            previous = cache_data.get("count", 0)
            previous_passing_ids = set(str(x) for x in cache_data.get("passing_ids", []))
        except Exception:
            previous = 0

    # Only notify if progress increased
    if passing > previous:
        # Find which features are now passing
        completed_tests = []
        current_passing_ids = []

        # Get all passing features
        all_passing = get_all_passing_features(project_dir, project_name)
        for feature in all_passing:
            feature_id = str(feature.get("id"))
            current_passing_ids.append(feature_id)
            if feature_id not in previous_passing_ids:
                # This feature is newly passing
                name = feature.get("name", f"Feature #{feature_id}")
                category = feature.get("category", "")
                if category:
                    completed_tests.append(f"{category} {name}")
                else:
                    completed_tests.append(name)

        payload = {
            "event": "test_progress",
            "passing": passing,
            "total": total,
            "percentage": round((passing / total) * 100, 1) if total > 0 else 0,
            "previous_passing": previous,
            "tests_completed_this_session": passing - previous,
            "completed_tests": completed_tests,
            "project": project_dir.name,
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }

        try:
            req = urllib.request.Request(
                WEBHOOK_URL,
                data=json.dumps([payload]).encode("utf-8"),  # n8n expects array
                headers={"Content-Type": "application/json"},
            )
            urllib.request.urlopen(req, timeout=5)
        except Exception as e:
            print(f"[Webhook notification failed: {e}]")

        # Update cache with count and passing IDs
        cache_file.write_text(
            json.dumps({"count": passing, "passing_ids": current_passing_ids})
        )
    else:
        # Update cache even if no change (for initial state)
        if not cache_file.exists():
            all_passing = get_all_passing_features(project_dir, project_name)
            current_passing_ids = [str(f.get("id")) for f in all_passing]
            cache_file.write_text(
                json.dumps({"count": passing, "passing_ids": current_passing_ids})
            )


def print_session_header(session_num: int, is_initializer: bool) -> None:
    """Print a formatted header for the session."""
    session_type = "INITIALIZER" if is_initializer else "CODING AGENT"

    print("\n" + "=" * 70)
    print(f"  SESSION {session_num}: {session_type}")
    print("=" * 70)
    print()


def print_progress_summary(project_dir: Path, project_name: str | None = None) -> None:
    """Print a summary of current progress."""
    passing, in_progress, total = count_passing_tests(project_dir, project_name)

    if total > 0:
        percentage = (passing / total) * 100
        status_parts = [f"{passing}/{total} tests passing ({percentage:.1f}%)"]
        if in_progress > 0:
            status_parts.append(f"{in_progress} in progress")
        print(f"\nProgress: {', '.join(status_parts)}")
        send_progress_webhook(passing, total, project_dir, project_name)
    else:
        print("\nProgress: No features yet")
