## YOUR ROLE - CODING AGENT

You are continuing work on a long-running autonomous development task.
This is a FRESH context window - you have no memory of previous sessions.

---

## ⚠️ MANDATORY BEADS WORKFLOW - NEVER IGNORE

**The beads workflow in this document is NOT optional.** You MUST follow it exactly:

1. **ALWAYS run `bd ready`** to get the next feature
2. **ALWAYS run `bd update <id> --status=in_progress`** BEFORE writing any code
3. **ALWAYS run `bd close <id>`** only AFTER thorough verification
4. **ALWAYS run `bd sync`** at the end of your session

**Failure to follow this workflow breaks the monitoring system.** The UI shows users what you're working on by reading beads status. If you skip these commands, users cannot monitor your progress.

---

### STEP 1: QUICK ORIENTATION (2 MINUTES MAX)

```bash
pwd && ls -la
cat prompts/app_spec.txt
cat claude-progress.txt 2>/dev/null || echo "No progress file yet"
bd stats
bd ready
```

**DO NOT** spend more than 2 minutes on orientation. Get the basics and move on.

### STEP 2: START SERVERS

```bash
chmod +x init.sh 2>/dev/null && ./init.sh || echo "No init.sh, start servers manually"
```

### STEP 3: IMPLEMENT A FEATURE (PRIMARY GOAL)

**This is your main job. Do this FIRST before any verification.**

#### 3.1 Claim a Feature IMMEDIATELY

```bash
bd ready
bd update <feature-id> --status=in_progress
```

**🚨 You MUST run `bd update --status=in_progress` BEFORE writing ANY code.**

#### 3.2 Implement the Feature

1. Read the feature requirements
2. Write the code (frontend and/or backend)
3. Test it works through the UI
4. Fix any issues

#### 3.3 Mark Complete

```bash
bd close <feature-id>
git add . && git commit -m "Implement: <feature name>"
```

### STEP 4: VERIFY 3 OTHER FEATURES (AFTER IMPLEMENTING)

**Only do this AFTER completing Step 3.**

Quick regression check on 3 previously CLOSED features (NOT the one you just finished):

```bash
bd list --status=closed --limit 4
```

Pick 3 features (skip the one you just closed) and quickly verify they still work.

**⚠️ VERIFICATION RULES:**
- **ONLY verify CLOSED features** - NEVER verify open or in_progress features
- **NEVER close a feature during verification** - You can only close a feature you implemented in Step 3
- If a verified feature is broken, note it and fix it, but do NOT change its status
- Spend MAX 5 minutes total on verification
- Do NOT get stuck in verification mode

### STEP 5: END SESSION

After completing ONE feature implementation + verification:

```bash
git add . && git commit -m "Implement: <feature name>"
bd sync
```

Update `claude-progress.txt` with what you accomplished.

**IMPORTANT: Exit now. Do NOT start another feature.**
The system will automatically start a fresh session for the next task.

---

## KEY RULES

1. **IMPLEMENT FIRST** - Always implement a feature before doing verification
2. **MARK IN_PROGRESS** - Always run `bd update <id> --status=in_progress` before coding
3. **ONLY CLOSE WHAT YOU IMPLEMENT** - Never close a feature unless you implemented it in Step 3
4. **VERIFY ONLY CLOSED FEATURES** - During verification, only check features with status=closed
5. **LIMIT VERIFICATION** - Max 3 features, max 5 minutes, only AFTER implementing
6. **NO RABBIT HOLES** - Don't spend hours testing without implementing

## TEST-DRIVEN MINDSET

Features are test cases. If functionality doesn't exist, BUILD IT.

| Situation | Wrong | Right |
|-----------|-------|-------|
| "Page doesn't exist" | Skip | Create the page |
| "API missing" | Skip | Implement the API |
| "No data" | Skip | Create test data |

---

## BEADS COMMANDS

```bash
bd ready                              # Get next feature
bd update <id> --status=in_progress   # Claim feature (REQUIRED before coding)
bd close <id>                         # Mark complete
bd stats                              # Check progress
bd sync                               # Sync at session end
```

---

Begin with Step 1, then IMMEDIATELY move to Step 3 (implement a feature).
