/**
 * Beads Commands Script
 * =====================
 *
 * Executes beads operations inside the container.
 * Reads JSON command from stdin, outputs JSON result.
 *
 * Usage:
 *     echo '{"action": "get", "feature_id": "feat-1"}' | node /app/dist/beads_commands.js
 *
 * Actions:
 *     - list: List all features (same as feature_status.ts)
 *     - get: Get single feature by ID
 *     - create: Create new feature
 *     - update: Update feature fields
 *     - delete: Delete feature
 *     - skip: Skip feature (set priority to P4)
 *     - reopen: Reopen closed feature
 *     - init: Initialize beads if not already
 */

import * as fs from "fs";
import * as path from "path";
import { spawn, SpawnSyncReturns, spawnSync } from "child_process";

const PROJECT_DIR = "/project";
const BEADS_DIR = path.join(PROJECT_DIR, ".beads");

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
  passes: boolean;
  in_progress: boolean;
}

interface Stats {
  pending: number;
  in_progress: number;
  done: number;
  total: number;
  percentage: number;
}

interface CommandResult {
  success: boolean;
  error?: string;
  message?: string;
  feature?: Feature;
  features?: Feature[];
  stats?: Stats;
  feature_id?: string;
  old_priority?: number;
  new_priority?: number;
}

interface Command {
  action: string;
  feature_id?: string;
  data?: {
    name?: string;
    description?: string;
    category?: string;
    steps?: string[];
    priority?: number;
  };
}

/**
 * Run bd CLI command.
 */
function runBd(args: string[]): SpawnSyncReturns<string> {
  return spawnSync("bd", args, {
    cwd: PROJECT_DIR,
    encoding: "utf8",
  });
}

/**
 * Parse JSON from bd CLI output.
 */
function parseJsonOutput(
  result: SpawnSyncReturns<string>
): [unknown, string | null] {
  try {
    return [JSON.parse(result.stdout), null];
  } catch (e) {
    const stderrPreview = result.stderr
      ? result.stderr.slice(0, 200)
      : "none";
    const errorMsg = `JSON parse error: ${e}. stdout: ${
      result.stdout ? result.stdout.slice(0, 100) : "empty"
    }. stderr: ${stderrPreview}`;
    return [[], errorMsg];
  }
}

/**
 * Check if beads is initialized.
 */
function isInitialized(): boolean {
  return (
    fs.existsSync(BEADS_DIR) &&
    fs.existsSync(path.join(BEADS_DIR, "config.yaml"))
  );
}

/**
 * Initialize beads in project directory.
 */
function initBeads(): boolean {
  if (isInitialized()) {
    return true;
  }
  const result = runBd(["init", "--prefix", "feat"]);
  return result.status === 0;
}

/**
 * Convert numeric priority to beads P0-P4 format.
 */
function priorityToBeads(priority: number): string {
  if (priority <= 0) return "P0";
  if (priority === 1) return "P1";
  if (priority === 2) return "P2";
  if (priority === 3) return "P3";
  return "P4";
}

/**
 * Convert beads P0-P4 format to numeric priority.
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
 * Append steps as markdown checklist to description.
 */
function stepsToDescription(description: string, steps: string[]): string {
  if (!steps || steps.length === 0) {
    return description;
  }
  const stepsMd =
    "\n\n## Steps\n" + steps.map((step) => `- [ ] ${step}`).join("\n");
  return description + stepsMd;
}

/**
 * Convert beads issue to feature format.
 */
function issueToFeature(issue: Issue): Feature {
  const labels = issue.labels ?? [];
  const category = extractLabelValue(labels, "category") ?? "";

  const priorityLabel = extractLabelValue(labels, "priority");
  let priority: number;
  if (priorityLabel && /^\d+$/.test(priorityLabel)) {
    priority = parseInt(priorityLabel, 10);
  } else {
    priority = beadsToPriority(issue.priority);
  }

  const fullDescription = issue.description ?? "";
  const [description, steps] = parseStepsFromDescription(fullDescription);

  const status = issue.status ?? "open";

  return {
    id: issue.id ?? "",
    priority,
    category,
    name: issue.title ?? "",
    description,
    steps,
    status,
    passes: status === "closed",
    in_progress: status === "in_progress",
  };
}

// =============================================================================
// Actions
// =============================================================================

/**
 * List all features.
 */
function actionList(): CommandResult {
  const jsonlPath = path.join(BEADS_DIR, "issues.jsonl");
  if (!fs.existsSync(jsonlPath)) {
    return {
      success: true,
      features: [],
      stats: {
        pending: 0,
        in_progress: 0,
        done: 0,
        total: 0,
        percentage: 0.0,
      },
    };
  }

  const issues: Issue[] = [];
  const content = fs.readFileSync(jsonlPath, "utf8");
  for (const line of content.split("\n")) {
    const trimmedLine = line.trim();
    if (trimmedLine) {
      try {
        issues.push(JSON.parse(trimmedLine) as Issue);
      } catch {
        continue;
      }
    }
  }

  let pending = 0;
  let inProgress = 0;
  let done = 0;
  const features: Feature[] = [];

  for (const issue of issues) {
    const feature = issueToFeature(issue);
    features.push(feature);
    if (feature.passes) {
      done++;
    } else if (feature.in_progress) {
      inProgress++;
    } else {
      pending++;
    }
  }

  const total = pending + inProgress + done;
  const percentage = total > 0 ? Math.round((done / total) * 1000) / 10 : 0.0;

  return {
    success: true,
    features,
    stats: {
      pending,
      in_progress: inProgress,
      done,
      total,
      percentage,
    },
  };
}

/**
 * Get a single feature by ID.
 */
function actionGet(featureId: string): CommandResult {
  const result = runBd(["show", featureId, "--json"]);
  if (result.status !== 0) {
    return {
      success: false,
      error: `Feature ${featureId} not found: ${result.stderr}`,
    };
  }

  const [output, parseError] = parseJsonOutput(result);
  if (parseError) {
    return {
      success: false,
      error: `Failed to parse feature data: ${parseError}`,
    };
  }

  let feature: Feature;
  if (Array.isArray(output) && output.length > 0) {
    feature = issueToFeature(output[0] as Issue);
  } else if (output && typeof output === "object" && !Array.isArray(output)) {
    feature = issueToFeature(output as Issue);
  } else {
    return {
      success: false,
      error: `Feature ${featureId} not found (empty response)`,
    };
  }

  return { success: true, feature };
}

/**
 * Create a new feature.
 */
function actionCreate(data: Command["data"]): CommandResult {
  if (!isInitialized()) {
    if (!initBeads()) {
      return { success: false, error: "Failed to initialize beads" };
    }
  }

  const name = data?.name ?? "";
  const description = data?.description ?? "";
  const category = data?.category ?? "";
  const steps = data?.steps ?? [];
  const priority = data?.priority ?? 999;

  if (!name) {
    return { success: false, error: "Name is required" };
  }

  const beadsPriority = priorityToBeads(priority);
  const fullDescription = stepsToDescription(description, steps);
  const labels = [`category:${category}`, `priority:${priority}`];

  const result = runBd([
    "create",
    "--title",
    name,
    "--description",
    fullDescription,
    "--priority",
    beadsPriority,
    "--labels",
    labels.join(","),
    "--type",
    "task",
    "--json",
  ]);

  if (result.status !== 0) {
    return { success: false, error: `Failed to create feature: ${result.stderr}` };
  }

  const [output, parseError] = parseJsonOutput(result);
  if (parseError) {
    return {
      success: false,
      error: `Feature may have been created but failed to parse response: ${parseError}`,
    };
  }

  const featureId =
    typeof output === "object" && output !== null && "id" in output
      ? (output as { id: string }).id
      : null;

  if (!featureId) {
    return { success: false, error: "Feature created but no ID returned" };
  }

  // Get the created feature
  const getResult = actionGet(featureId);
  if (getResult.success) {
    return { success: true, feature: getResult.feature };
  }

  return { success: true, feature_id: featureId };
}

/**
 * Update a feature's fields.
 */
function actionUpdate(featureId: string, data: Command["data"]): CommandResult {
  // Get current feature
  const currentResult = actionGet(featureId);
  if (!currentResult.success) {
    return currentResult;
  }

  const current = currentResult.feature!;
  const args = ["update", featureId];

  const name = data?.name;
  const description = data?.description;
  const steps = data?.steps;
  const priority = data?.priority;
  const category = data?.category;

  if (name !== undefined) {
    args.push("--title", name);
  }

  // Build full description with steps
  if (description !== undefined || steps !== undefined) {
    const newDescription = description ?? current.description;
    const newSteps = steps ?? current.steps;
    const fullDescription = stepsToDescription(newDescription, newSteps);
    args.push("--description", fullDescription);
  }

  if (priority !== undefined) {
    const beadsPriority = priorityToBeads(priority);
    args.push("--priority", beadsPriority);
  }

  const result = runBd(args);
  if (result.status !== 0) {
    return { success: false, error: `Failed to update feature: ${result.stderr}` };
  }

  // Update labels if category or priority changed
  if (category !== undefined) {
    const oldCategory = current.category;
    if (oldCategory) {
      runBd(["label", featureId, "--remove", `category:${oldCategory}`]);
    }
    runBd(["label", featureId, "--add", `category:${category}`]);
  }

  if (priority !== undefined) {
    const oldPriority = current.priority;
    runBd(["label", featureId, "--remove", `priority:${oldPriority}`]);
    runBd(["label", featureId, "--add", `priority:${priority}`]);
  }

  // Get updated feature
  return actionGet(featureId);
}

/**
 * Delete a feature.
 */
function actionDelete(featureId: string): CommandResult {
  const result = runBd(["delete", featureId, "--force"]);
  if (result.status !== 0) {
    return { success: false, error: `Failed to delete feature: ${result.stderr}` };
  }

  return { success: true, message: `Feature ${featureId} deleted` };
}

/**
 * Skip a feature by setting priority to P4.
 */
function actionSkip(featureId: string): CommandResult {
  const currentResult = actionGet(featureId);
  if (!currentResult.success) {
    return currentResult;
  }

  const current = currentResult.feature!;

  if (current.passes) {
    return {
      success: false,
      error: "Cannot skip a feature that is already passing",
    };
  }

  const oldPriority = current.priority;

  // Update priority to P4 and clear in_progress
  const result = runBd(["update", featureId, "--priority=P4", "--status=open"]);
  if (result.status !== 0) {
    return { success: false, error: `Failed to skip feature: ${result.stderr}` };
  }

  // Update priority label
  const newPriority = 9999;
  runBd(["label", featureId, "--remove", `priority:${oldPriority}`]);
  runBd(["label", featureId, "--add", `priority:${newPriority}`]);

  return {
    success: true,
    message: `Feature '${current.name}' moved to end of queue`,
    old_priority: oldPriority,
    new_priority: newPriority,
  };
}

/**
 * Reopen a closed feature.
 */
function actionReopen(featureId: string): CommandResult {
  const result = runBd(["reopen", featureId]);
  if (result.status !== 0) {
    return { success: false, error: `Failed to reopen feature: ${result.stderr}` };
  }

  return actionGet(featureId);
}

/**
 * Initialize beads if not already.
 */
function actionInit(): CommandResult {
  if (isInitialized()) {
    return { success: true, message: "Already initialized" };
  }

  if (initBeads()) {
    return { success: true, message: "Beads initialized" };
  } else {
    return { success: false, error: "Failed to initialize beads" };
  }
}

/**
 * Handle a beads action from a dict.
 */
function handleAction(command: Command): CommandResult {
  const action = command.action ?? "";

  switch (action) {
    case "list":
      return actionList();
    case "get":
      if (!command.feature_id) {
        return { success: false, error: "feature_id required" };
      }
      return actionGet(command.feature_id);
    case "create":
      return actionCreate(command.data ?? {});
    case "update":
      if (!command.feature_id) {
        return { success: false, error: "feature_id required" };
      }
      return actionUpdate(command.feature_id, command.data ?? {});
    case "delete":
      if (!command.feature_id) {
        return { success: false, error: "feature_id required" };
      }
      return actionDelete(command.feature_id);
    case "skip":
      if (!command.feature_id) {
        return { success: false, error: "feature_id required" };
      }
      return actionSkip(command.feature_id);
    case "reopen":
      if (!command.feature_id) {
        return { success: false, error: "feature_id required" };
      }
      return actionReopen(command.feature_id);
    case "init":
      return actionInit();
    default:
      return { success: false, error: `Unknown action: ${action}` };
  }
}

// =============================================================================
// Main
// =============================================================================

/**
 * Read all input from stdin.
 */
async function readStdin(): Promise<string> {
  return new Promise((resolve, reject) => {
    let data = "";
    process.stdin.setEncoding("utf8");
    process.stdin.on("data", (chunk) => {
      data += chunk;
    });
    process.stdin.on("end", () => {
      resolve(data);
    });
    process.stdin.on("error", reject);
  });
}

async function main(): Promise<void> {
  try {
    // Read command from stdin
    const inputData = (await readStdin()).trim();
    if (!inputData) {
      console.log(JSON.stringify({ success: false, error: "No input provided" }));
      process.exit(1);
    }

    let command: Command;
    try {
      command = JSON.parse(inputData) as Command;
    } catch (e) {
      console.log(JSON.stringify({ success: false, error: `Invalid JSON: ${e}` }));
      process.exit(1);
    }

    const result = handleAction(command);
    console.log(JSON.stringify(result));
  } catch (e) {
    console.log(JSON.stringify({ success: false, error: String(e) }));
    process.exit(1);
  }
}

main();
