"""
Progress Tracking Utilities
===========================

Functions for tracking and displaying progress of the autonomous coding agent.
Uses cached feature data from container polling.
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
    Check if the project has features in beads.

    This is used to determine if the initializer agent needs to run.

    Returns True if .beads/ exists with issues.
    Returns False if no features exist (initializer needs to run).
    """
    # Try cache first if project_name provided (avoids permission issues)
    if project_name:
        try:
            from server.services.feature_poller import get_cached_stats

            stats = get_cached_stats(project_name)
            if stats.get("total", 0) > 0:
                return True
        except ImportError:
            pass  # Server modules not available

    # Direct JSONL check
    issues_file = project_dir / ".beads" / "issues.jsonl"
    if issues_file.exists():
        try:
            with open(issues_file, 'r') as f:
                for line in f:
                    if line.strip():
                        return True  # At least one issue exists
        except (PermissionError, OSError):
            pass  # Can't read - try config fallback

    # Check if .beads directory exists with config (beads initialized)
    config_file = project_dir / ".beads" / "config.yaml"
    if config_file.exists():
        # Beads is initialized, may have issues we can't read
        return True

    return False


def has_open_features(project_dir: Path, project_name: str | None = None) -> bool:
    """
    Check if the project has any open or in_progress features.

    This is used to determine if the overseer agent should run.
    Returns True if there are pending or in_progress features.
    Returns False if all features are closed (overseer should run).

    Args:
        project_dir: Directory containing the project
        project_name: Optional project name for cache lookup
    """
    # Try cache first if project_name provided (avoids permission issues)
    if project_name:
        try:
            from server.services.feature_poller import get_cached_stats

            stats = get_cached_stats(project_name)
            open_count = stats.get("pending", 0) + stats.get("in_progress", 0)
            return open_count > 0
        except ImportError:
            pass  # Server modules not available

    # Fallback: Direct JSONL check
    issues_file = project_dir / ".beads" / "issues.jsonl"
    if issues_file.exists():
        try:
            with open(issues_file, 'r') as f:
                for line in f:
                    if line.strip():
                        try:
                            issue = json.loads(line)
                            status = issue.get("status", "open")
                            if status in ("open", "in_progress"):
                                return True
                        except json.JSONDecodeError:
                            continue
        except (PermissionError, OSError):
            pass  # Can't read file

    return False


def count_passing_tests(project_dir: Path, project_name: str | None = None) -> tuple[int, int, int]:
    """
    Count passing, in_progress, and total tests.

    Uses cached data from feature_poller. This avoids permission issues
    when container is running (files may be owned by container user).

    Args:
        project_dir: Directory containing the project
        project_name: Optional project name for cache lookup

    Returns:
        (passing_count, in_progress_count, total_count)
    """
    # Try cache if project_name provided
    if project_name:
        try:
            from server.services.feature_poller import get_cached_stats

            stats = get_cached_stats(project_name)
            if stats.get("total", 0) > 0:
                return (
                    stats.get("done", 0),
                    stats.get("in_progress", 0),
                    stats.get("total", 0),
                )
        except ImportError:
            pass  # Server modules not available

    # Fallback: try to read JSONL directly (may fail with permission error)
    issues_file = project_dir / ".beads" / "issues.jsonl"
    if issues_file.exists():
        try:
            passing = 0
            in_progress = 0
            total = 0
            with open(issues_file, 'r') as f:
                for line in f:
                    if line.strip():
                        try:
                            issue = json.loads(line)
                            total += 1
                            status = issue.get("status", "open")
                            if status == "closed":
                                passing += 1
                            elif status == "in_progress":
                                in_progress += 1
                        except json.JSONDecodeError:
                            continue
            return passing, in_progress, total
        except (PermissionError, OSError):
            pass  # Can't read file

    return 0, 0, 0


def get_all_passing_features(project_dir: Path, project_name: str | None = None) -> list[dict]:
    """
    Get all passing features for webhook notifications.

    Uses cached data when available.

    Args:
        project_dir: Directory containing the project
        project_name: Optional project name for cache lookup

    Returns:
        List of dicts with id, category, name for each passing feature
    """
    # Try cache if project_name provided
    if project_name:
        try:
            from server.services.feature_poller import get_cached_features

            cached = get_cached_features(project_name)
            passing = []
            for f in cached:
                if f.get("passes") or f.get("status") == "closed":
                    passing.append({
                        "id": f.get("id", ""),
                        "category": f.get("category", ""),
                        "name": f.get("name", ""),
                    })
            return passing
        except ImportError:
            pass  # Server modules not available

    # Fallback: try to read JSONL directly
    issues_file = project_dir / ".beads" / "issues.jsonl"
    if issues_file.exists():
        try:
            passing = []
            with open(issues_file, 'r') as f:
                for line in f:
                    if line.strip():
                        try:
                            issue = json.loads(line)
                            if issue.get("status") == "closed":
                                # Extract category from labels
                                category = ""
                                for label in issue.get("labels", []):
                                    if label.startswith("category:"):
                                        category = label[9:]
                                        break
                                passing.append({
                                    "id": issue.get("id", ""),
                                    "category": category,
                                    "name": issue.get("title", ""),
                                })
                        except json.JSONDecodeError:
                            continue
            return passing
        except (PermissionError, OSError):
            pass  # Can't read file

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
