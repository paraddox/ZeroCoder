/**
 * Feature Status Query Script
 * ===========================
 *
 * Outputs feature status from beads as JSON for host polling.
 * Designed to be run via: docker exec -u coder <container> node /app/dist/feature_status.js
 *
 * This script reads the beads issues.jsonl file directly and outputs
 * a JSON object with feature stats and full feature list.
 */

import * as fs from "fs";
import * as path from "path";

const BEADS_DIR = "/project/.beads";
const ISSUES_FILE = path.join(BEADS_DIR, "issues.jsonl");

interface Issue {
  id?: string;
  title?: string;
  description?: string;
  status?: string;
  priority?: string | number;
  labels?: string[];
}

interface Feature {
  id: string;
  priority: number;
  category: string;
  name: string;
  description: string;
  steps: string[];
  status: string;
}

interface Stats {
  pending: number;
  in_progress: number;
  done: number;
  total: number;
  percentage: number;
}

interface StatusResult {
  success: boolean;
  error?: string;
  stats: Stats;
  features: Feature[];
}

/**
 * Convert beads P0-P4 format or numeric priority to int.
 */
function beadsToPriority(beadsPriority: string | number | undefined): number {
  if (typeof beadsPriority === "number") {
    return beadsPriority;
  }
  if (typeof beadsPriority === "string") {
    if (/^\d+$/.test(beadsPriority)) {
      return parseInt(beadsPriority, 10);
    }
    const mapping: Record<string, number> = {
      P0: 0,
      P1: 1,
      P2: 2,
      P3: 3,
      P4: 4,
    };
    return mapping[beadsPriority.toUpperCase()] ?? 4;
  }
  return 4;
}

/**
 * Extract value from a label like 'category:value'.
 */
function extractLabelValue(
  labels: string[] | undefined,
  prefix: string
): string | null {
  if (!labels) return null;
  for (const label of labels) {
    if (label.startsWith(`${prefix}:`)) {
      return label.slice(prefix.length + 1);
    }
  }
  return null;
}

/**
 * Extract steps checklist from description.
 */
function parseStepsFromDescription(
  description: string
): [string, string[]] {
  if (!description.includes("## Steps")) {
    return [description, []];
  }

  const parts = description.split("## Steps");
  const baseDescription = parts[0]?.trimEnd() ?? "";
  const stepsSection = parts[1] ?? "";

  const steps: string[] = [];
  for (const line of stepsSection.trim().split("\n")) {
    const trimmedLine = line.trim();
    if (trimmedLine.startsWith("- [ ]")) {
      steps.push(trimmedLine.slice(5).trim());
    } else if (trimmedLine.startsWith("- [x]")) {
      steps.push(trimmedLine.slice(5).trim());
    }
  }

  return [baseDescription, steps];
}

/**
 * Read issues directly from JSONL file.
 */
function readIssues(): Issue[] {
  if (!fs.existsSync(ISSUES_FILE)) {
    return [];
  }

  const issues: Issue[] = [];
  try {
    const content = fs.readFileSync(ISSUES_FILE, "utf8");
    for (const line of content.split("\n")) {
      const trimmedLine = line.trim();
      if (!trimmedLine) continue;
      try {
        issues.push(JSON.parse(trimmedLine) as Issue);
      } catch {
        // Skip invalid JSON lines
        continue;
      }
    }
  } catch (e) {
    console.log(
      JSON.stringify({
        success: false,
        error: `Failed to read issues file: ${e}`,
        stats: { pending: 0, in_progress: 0, done: 0, total: 0, percentage: 0.0 },
        features: [],
      })
    );
    process.exit(1);
  }

  return issues;
}

/**
 * Get full feature status.
 */
function getStatus(): StatusResult {
  const issues = readIssues();

  let pending = 0;
  let inProgress = 0;
  let done = 0;
  const features: Feature[] = [];

  for (const issue of issues) {
    const status = issue.status ?? "open";

    if (status === "closed") {
      done++;
    } else if (status === "in_progress") {
      inProgress++;
    } else {
      pending++;
    }

    // Extract category from labels
    const labels = issue.labels ?? [];
    const category = extractLabelValue(labels, "category") ?? "";

    // Parse priority from label or beads priority field
    const priorityLabel = extractLabelValue(labels, "priority");
    let priority: number;
    if (priorityLabel && /^\d+$/.test(priorityLabel)) {
      priority = parseInt(priorityLabel, 10);
    } else {
      priority = beadsToPriority(issue.priority);
    }

    // Parse steps from description
    const fullDescription = issue.description ?? "";
    const [description, steps] = parseStepsFromDescription(fullDescription);

    features.push({
      id: issue.id ?? "",
      priority,
      category,
      name: issue.title ?? "",
      description,
      steps,
      status,
    });
  }

  const total = pending + inProgress + done;
  const percentage = total > 0 ? Math.round((done / total) * 1000) / 10 : 0.0;

  return {
    success: true,
    stats: {
      pending,
      in_progress: inProgress,
      done,
      total,
      percentage,
    },
    features,
  };
}

// Main
try {
  const result = getStatus();
  console.log(JSON.stringify(result));
} catch (e) {
  console.log(
    JSON.stringify({
      success: false,
      error: String(e),
      stats: { pending: 0, in_progress: 0, done: 0, total: 0, percentage: 0.0 },
      features: [],
    })
  );
  process.exit(1);
}
