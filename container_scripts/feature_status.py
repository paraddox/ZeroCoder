#!/usr/bin/env python3
"""
Feature Status Query Script
===========================

Outputs feature status from beads as JSON for host polling.
Designed to be run via: docker exec -u coder <container> python /app/feature_status.py

This script reads the beads issues.jsonl file directly and outputs
a JSON object with feature stats and full feature list.
"""

import json
import sys
from pathlib import Path

BEADS_DIR = Path("/project/.beads")
ISSUES_FILE = BEADS_DIR / "issues.jsonl"


def beads_to_priority(beads_priority: str | int) -> int:
    """Convert beads P0-P4 format or numeric priority to int."""
    if isinstance(beads_priority, int):
        return beads_priority
    if isinstance(beads_priority, str) and beads_priority.isdigit():
        return int(beads_priority)
    mapping = {"P0": 0, "P1": 1, "P2": 2, "P3": 3, "P4": 4}
    return mapping.get(str(beads_priority).upper(), 4)


def extract_label_value(labels: list[str], prefix: str) -> str | None:
    """Extract value from a label like 'category:value'."""
    for label in labels:
        if label.startswith(f"{prefix}:"):
            return label[len(prefix) + 1:]
    return None


def parse_steps_from_description(description: str) -> tuple[str, list[str]]:
    """Extract steps checklist from description."""
    if "## Steps" not in description:
        return description, []

    parts = description.split("## Steps", 1)
    base_description = parts[0].rstrip()
    steps_section = parts[1] if len(parts) > 1 else ""

    steps = []
    for line in steps_section.strip().split("\n"):
        line = line.strip()
        if line.startswith("- [ ]"):
            steps.append(line[5:].strip())
        elif line.startswith("- [x]"):
            steps.append(line[5:].strip())

    return base_description, steps


def read_issues() -> list[dict]:
    """Read issues directly from JSONL file."""
    if not ISSUES_FILE.exists():
        return []

    issues = []
    try:
        with open(ISSUES_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    issues.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except (PermissionError, OSError) as e:
        print(json.dumps({
            "success": False,
            "error": f"Failed to read issues file: {e}",
            "stats": {"pending": 0, "in_progress": 0, "done": 0, "total": 0, "percentage": 0.0},
            "features": [],
        }))
        sys.exit(1)

    return issues


def get_status() -> dict:
    """Get full feature status."""
    issues = read_issues()

    pending = 0
    in_progress = 0
    done = 0
    features = []

    for issue in issues:
        status = issue.get("status", "open")

        if status == "closed":
            done += 1
        elif status == "in_progress":
            in_progress += 1
        else:
            pending += 1

        # Extract category from labels
        labels = issue.get("labels", [])
        category = extract_label_value(labels, "category") or ""

        # Parse priority from label or beads priority field
        priority_label = extract_label_value(labels, "priority")
        if priority_label and priority_label.isdigit():
            priority = int(priority_label)
        else:
            priority = beads_to_priority(issue.get("priority", "P4"))

        # Parse steps from description
        full_description = issue.get("description", "")
        description, steps = parse_steps_from_description(full_description)

        features.append({
            "id": issue.get("id", ""),
            "priority": priority,
            "category": category,
            "name": issue.get("title", ""),
            "description": description,
            "steps": steps,
            "status": status,
        })

    total = pending + in_progress + done
    percentage = round((done / total) * 100, 1) if total > 0 else 0.0

    return {
        "success": True,
        "stats": {
            "pending": pending,
            "in_progress": in_progress,
            "done": done,
            "total": total,
            "percentage": percentage,
        },
        "features": features,
    }


if __name__ == "__main__":
    try:
        result = get_status()
        print(json.dumps(result))
    except Exception as e:
        print(json.dumps({
            "success": False,
            "error": str(e),
            "stats": {"pending": 0, "in_progress": 0, "done": 0, "total": 0, "percentage": 0.0},
            "features": [],
        }))
        sys.exit(1)
