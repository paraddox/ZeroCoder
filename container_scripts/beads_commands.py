#!/usr/bin/env python3
"""
Beads Commands Script
=====================

Executes beads operations inside the container.
Reads JSON command from stdin, outputs JSON result.

Usage:
    echo '{"action": "get", "feature_id": "feat-1"}' | python /app/beads_commands.py

Actions:
    - list: List all features (same as feature_status.py)
    - get: Get single feature by ID
    - create: Create new feature
    - update: Update feature fields
    - delete: Delete feature
    - skip: Skip feature (set priority to P4)
    - reopen: Reopen closed feature
    - init: Initialize beads if not already
"""

import json
import subprocess
import sys
from pathlib import Path

PROJECT_DIR = Path("/project")
BEADS_DIR = PROJECT_DIR / ".beads"


def run_bd(args: list[str], check: bool = False) -> subprocess.CompletedProcess:
    """Run bd CLI command."""
    return subprocess.run(
        ["bd"] + args,
        cwd=PROJECT_DIR,
        capture_output=True,
        text=True,
        check=check,
    )


def parse_json_output(result: subprocess.CompletedProcess) -> list | dict:
    """Parse JSON from bd CLI output."""
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return []


def is_initialized() -> bool:
    """Check if beads is initialized."""
    return BEADS_DIR.exists() and (BEADS_DIR / "config.yaml").exists()


def init_beads() -> bool:
    """Initialize beads in project directory."""
    if is_initialized():
        return True
    result = run_bd(["init", "--prefix", "feat"])
    return result.returncode == 0


def priority_to_beads(priority: int) -> str:
    """Convert numeric priority to beads P0-P4 format."""
    if priority <= 0:
        return "P0"
    elif priority == 1:
        return "P1"
    elif priority == 2:
        return "P2"
    elif priority == 3:
        return "P3"
    else:
        return "P4"


def beads_to_priority(beads_priority: str | int) -> int:
    """Convert beads P0-P4 format to numeric priority."""
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


def steps_to_description(description: str, steps: list[str]) -> str:
    """Append steps as markdown checklist to description."""
    if not steps:
        return description
    steps_md = "\n\n## Steps\n" + "\n".join(f"- [ ] {step}" for step in steps)
    return description + steps_md


def issue_to_feature(issue: dict) -> dict:
    """Convert beads issue to feature format."""
    labels = issue.get("labels", [])
    category = extract_label_value(labels, "category") or ""

    priority_label = extract_label_value(labels, "priority")
    if priority_label and priority_label.isdigit():
        priority = int(priority_label)
    else:
        priority = beads_to_priority(issue.get("priority", "P4"))

    full_description = issue.get("description", "")
    description, steps = parse_steps_from_description(full_description)

    status = issue.get("status", "open")

    return {
        "id": issue.get("id", ""),
        "priority": priority,
        "category": category,
        "name": issue.get("title", ""),
        "description": description,
        "steps": steps,
        "status": status,
        "passes": status == "closed",
        "in_progress": status == "in_progress",
    }


# =============================================================================
# Actions
# =============================================================================

def action_list() -> dict:
    """List all features."""
    # Read from JSONL for consistency
    jsonl_path = BEADS_DIR / "issues.jsonl"
    if not jsonl_path.exists():
        return {"success": True, "features": [], "stats": {
            "pending": 0, "in_progress": 0, "done": 0, "total": 0, "percentage": 0.0
        }}

    issues = []
    with open(jsonl_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    issues.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

    pending, in_progress, done = 0, 0, 0
    features = []

    for issue in issues:
        feature = issue_to_feature(issue)
        features.append(feature)
        if feature["passes"]:
            done += 1
        elif feature["in_progress"]:
            in_progress += 1
        else:
            pending += 1

    total = pending + in_progress + done
    percentage = round((done / total) * 100, 1) if total > 0 else 0.0

    return {
        "success": True,
        "features": features,
        "stats": {
            "pending": pending,
            "in_progress": in_progress,
            "done": done,
            "total": total,
            "percentage": percentage,
        },
    }


def action_get(feature_id: str) -> dict:
    """Get a single feature by ID."""
    result = run_bd(["show", feature_id, "--json"])
    if result.returncode != 0:
        return {"success": False, "error": f"Feature {feature_id} not found"}

    output = parse_json_output(result)
    if isinstance(output, list) and output:
        feature = issue_to_feature(output[0])
    elif isinstance(output, dict) and output:
        feature = issue_to_feature(output)
    else:
        return {"success": False, "error": f"Feature {feature_id} not found"}

    return {"success": True, "feature": feature}


def action_create(data: dict) -> dict:
    """Create a new feature."""
    if not is_initialized():
        if not init_beads():
            return {"success": False, "error": "Failed to initialize beads"}

    name = data.get("name", "")
    description = data.get("description", "")
    category = data.get("category", "")
    steps = data.get("steps", [])
    priority = data.get("priority", 999)

    if not name:
        return {"success": False, "error": "Name is required"}

    beads_priority = priority_to_beads(priority)
    full_description = steps_to_description(description, steps)
    labels = [f"category:{category}", f"priority:{priority}"]

    result = run_bd([
        "create",
        "--title", name,
        "--description", full_description,
        "--priority", beads_priority,
        "--labels", ",".join(labels),
        "--type", "task",
        "--json",
    ])

    if result.returncode != 0:
        return {"success": False, "error": f"Failed to create feature: {result.stderr}"}

    output = parse_json_output(result)
    feature_id = output.get("id") if isinstance(output, dict) else None

    if not feature_id:
        return {"success": False, "error": "Feature created but no ID returned"}

    # Get the created feature
    get_result = action_get(feature_id)
    if get_result.get("success"):
        return {"success": True, "feature": get_result["feature"]}

    return {"success": True, "feature_id": feature_id}


def action_update(feature_id: str, data: dict) -> dict:
    """Update a feature's fields."""
    # Get current feature
    current_result = action_get(feature_id)
    if not current_result.get("success"):
        return current_result

    current = current_result["feature"]
    args = ["update", feature_id]

    name = data.get("name")
    description = data.get("description")
    steps = data.get("steps")
    priority = data.get("priority")
    category = data.get("category")

    if name is not None:
        args.extend(["--title", name])

    # Build full description with steps
    if description is not None or steps is not None:
        new_description = description if description is not None else current.get("description", "")
        new_steps = steps if steps is not None else current.get("steps", [])
        full_description = steps_to_description(new_description, new_steps)
        args.extend(["--description", full_description])

    if priority is not None:
        beads_priority = priority_to_beads(priority)
        args.extend(["--priority", beads_priority])

    result = run_bd(args)
    if result.returncode != 0:
        return {"success": False, "error": f"Failed to update feature: {result.stderr}"}

    # Update labels if category or priority changed
    if category is not None:
        old_category = current.get("category", "")
        if old_category:
            run_bd(["label", feature_id, "--remove", f"category:{old_category}"])
        run_bd(["label", feature_id, "--add", f"category:{category}"])

    if priority is not None:
        old_priority = current.get("priority", 999)
        run_bd(["label", feature_id, "--remove", f"priority:{old_priority}"])
        run_bd(["label", feature_id, "--add", f"priority:{priority}"])

    # Get updated feature
    return action_get(feature_id)


def action_delete(feature_id: str) -> dict:
    """Delete a feature."""
    result = run_bd(["delete", feature_id, "--force"])
    if result.returncode != 0:
        return {"success": False, "error": f"Failed to delete feature: {result.stderr}"}

    return {"success": True, "message": f"Feature {feature_id} deleted"}


def action_skip(feature_id: str) -> dict:
    """Skip a feature by setting priority to P4."""
    current_result = action_get(feature_id)
    if not current_result.get("success"):
        return current_result

    current = current_result["feature"]

    if current.get("passes"):
        return {"success": False, "error": "Cannot skip a feature that is already passing"}

    old_priority = current.get("priority", 0)

    # Update priority to P4 and clear in_progress
    result = run_bd(["update", feature_id, "--priority=P4", "--status=open"])
    if result.returncode != 0:
        return {"success": False, "error": f"Failed to skip feature: {result.stderr}"}

    # Update priority label
    new_priority = 9999
    run_bd(["label", feature_id, "--remove", f"priority:{old_priority}"])
    run_bd(["label", feature_id, "--add", f"priority:{new_priority}"])

    return {
        "success": True,
        "message": f"Feature '{current.get('name', '')}' moved to end of queue",
        "old_priority": old_priority,
        "new_priority": new_priority,
    }


def action_reopen(feature_id: str) -> dict:
    """Reopen a closed feature."""
    result = run_bd(["reopen", feature_id])
    if result.returncode != 0:
        return {"success": False, "error": f"Failed to reopen feature: {result.stderr}"}

    return action_get(feature_id)


def action_init() -> dict:
    """Initialize beads if not already."""
    if is_initialized():
        return {"success": True, "message": "Already initialized"}

    if init_beads():
        return {"success": True, "message": "Beads initialized"}
    else:
        return {"success": False, "error": "Failed to initialize beads"}


# =============================================================================
# Main
# =============================================================================

def main():
    try:
        # Read command from stdin
        input_data = sys.stdin.read().strip()
        if not input_data:
            print(json.dumps({"success": False, "error": "No input provided"}))
            sys.exit(1)

        command = json.loads(input_data)
        action = command.get("action", "")

        if action == "list":
            result = action_list()
        elif action == "get":
            feature_id = command.get("feature_id", "")
            if not feature_id:
                result = {"success": False, "error": "feature_id required"}
            else:
                result = action_get(feature_id)
        elif action == "create":
            data = command.get("data", {})
            result = action_create(data)
        elif action == "update":
            feature_id = command.get("feature_id", "")
            data = command.get("data", {})
            if not feature_id:
                result = {"success": False, "error": "feature_id required"}
            else:
                result = action_update(feature_id, data)
        elif action == "delete":
            feature_id = command.get("feature_id", "")
            if not feature_id:
                result = {"success": False, "error": "feature_id required"}
            else:
                result = action_delete(feature_id)
        elif action == "skip":
            feature_id = command.get("feature_id", "")
            if not feature_id:
                result = {"success": False, "error": "feature_id required"}
            else:
                result = action_skip(feature_id)
        elif action == "reopen":
            feature_id = command.get("feature_id", "")
            if not feature_id:
                result = {"success": False, "error": "feature_id required"}
            else:
                result = action_reopen(feature_id)
        elif action == "init":
            result = action_init()
        else:
            result = {"success": False, "error": f"Unknown action: {action}"}

        print(json.dumps(result))

    except json.JSONDecodeError as e:
        print(json.dumps({"success": False, "error": f"Invalid JSON: {e}"}))
        sys.exit(1)
    except Exception as e:
        print(json.dumps({"success": False, "error": str(e)}))
        sys.exit(1)


if __name__ == "__main__":
    main()
