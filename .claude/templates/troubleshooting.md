# Troubleshooting Guide

Common problems and solutions for coding agents.

---

## Debugging Strategies

### When Stuck > 15 Minutes

1. **Check actual error messages** - Read logs, not just symptoms
2. **Simplify** - Remove complexity until it works, add back incrementally
3. **Isolate** - Test component in isolation
4. **Search codebase** - Similar patterns may already exist
5. **Add logging** - Print intermediate values to trace the issue
6. **Check AGENTS.md** - Solution may already be documented

### When Truly Blocked

Don't waste time. Document and exit:

```bash
# Commit partial work
git add .
git commit -m "WIP: $FEATURE_TITLE (blocked: [reason])" || true

# Keep in_progress
echo "## Blocked: $(date)" >> AGENTS.md
echo "- Feature: $FEATURE_ID" >> AGENTS.md
echo "- Reason: [specific blocker]" >> AGENTS.md
echo "- Attempted: [what you tried]" >> AGENTS.md

bd sync
```

Next session gets fresh context and may solve it.

---

## Merge Conflict Resolution

### Step-by-Step Process

```bash
# 1. Fetch latest main
git fetch origin main

# 2. Attempt merge
git merge origin/main --no-edit

# If conflicts:
# 3. See conflicted files
git diff --name-only --diff-filter=U

# 4. For each conflicted file, open and look for conflict markers:
# <<<<<<< HEAD
# your changes
# =======
# their changes
# >>>>>>> origin/main

# 5. Edit file to resolve (keep correct version, remove markers)

# 6. Mark as resolved
git add <resolved-file>

# 7. Complete merge
git commit -m "Resolve merge conflicts"
```

### Common Conflict Patterns

| Pattern | Resolution |
|---------|------------|
| Both modified same line | Choose correct version (usually yours) |
| Both added different code | Keep both if independent |
| File deleted vs modified | Usually keep the modification |
| Package-lock.json | Delete, run `npm install`, commit new lock |

### Avoid Conflicts

- Pull main before starting feature branch
- Small, focused features reduce conflict surface
- Communicate with other agents via AGENTS.md

---

## Common Errors

### "Cannot find module"

```bash
# Dependencies not installed
npm install
# or
pnpm install
```

### "Port already in use"

```bash
# Find and kill process
lsof -i :3000 | grep LISTEN | awk '{print $2}' | xargs kill -9
# Then restart server
```

### "Permission denied"

```bash
# Make script executable
chmod +x init.sh
```

### TypeScript Errors

```bash
# Check for type errors
npx tsc --noEmit

# Common fixes:
# - Add missing type annotations
# - Import missing types
# - Check for null/undefined
```

### ESLint Errors

```bash
# See all errors
npm run lint

# Auto-fix what's possible
npm run lint -- --fix
```

### Test Failures

```bash
# Run specific test to see detailed output
npm test -- --verbose <test-file>

# Common causes:
# - Async not awaited
# - Mock not cleaned up
# - Database state from previous test
```

---

## When to Exit vs Continue

### Exit Immediately

- Blocked on external dependency (API key, service down)
- Fundamental architecture issue discovered
- Feature requirements unclear/contradictory
- Same error after 3+ different approaches

### Continue Working

- Fixable error with clear solution
- Making progress (tests passing incrementally)
- Error is in code you just wrote

### Time Guidance

| Time Stuck | Action |
|------------|--------|
| < 15 min | Keep debugging |
| 15-30 min | Try different approach |
| 30-60 min | Simplify scope |
| > 60 min | Document and exit |

---

## Recovery Procedures

### Corrupted Git State

```bash
# Stash changes
git stash

# Reset to origin
git fetch origin
git reset --hard origin/main

# Restore changes
git stash pop
```

### Lost Work After Crash

Check for recovery files:
- `IMPLEMENTATION_PLAN.md` - May have partial progress
- `git reflog` - Shows recent commits
- `git stash list` - May have stashed changes

### Wrong Branch

```bash
# See current branch
git branch

# If on wrong branch with uncommitted changes
git stash
git checkout correct-branch
git stash pop
```

---

## Performance Issues

### Server Won't Start

1. Check port availability
2. Check logs for startup errors
3. Verify all dependencies installed
4. Check database connection

### Slow Operations

1. Check for missing database indexes
2. Look for N+1 query patterns
3. Check for unnecessary re-renders (React)
4. Profile with browser DevTools

---

## Environment Issues

### Node Version Mismatch

```bash
# Check version
node --version

# Use correct version (if nvm installed)
nvm use
```

### Missing Environment Variables

```bash
# Check what's set
env | grep -E 'DATABASE|API|SECRET'

# Set missing ones (check .env.example)
export DATABASE_URL="..."
```

### Database Connection Failed

```bash
# Check if database is running
pg_isready  # PostgreSQL
mysql -e "SELECT 1"  # MySQL

# Check connection string in .env
```

---

## When All Else Fails

1. Document everything you tried in AGENTS.md
2. Commit any partial work
3. Exit cleanly
4. Next session starts fresh with full context budget
