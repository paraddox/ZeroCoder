# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is an autonomous coding agent system with a React-based UI. It uses the Claude Agent SDK to build complete applications over multiple sessions using a two-agent pattern:

1. **Initializer Agent** - First session reads an app spec and creates features using beads issue tracking
2. **Coding Agent** - Subsequent sessions implement features one by one, marking them as passing

## Commands

### Quick Start

```bash
# Launch Web UI (serves pre-built React app)
start-app.sh      # Windows
./start-app.sh     # macOS/Linux
./start-app.sh -s #to stop all app service and remove all containers
```

### Python Backend (Manual)

```bash
# Create and activate virtual environment
python -m venv venv
venv\Scripts\activate  # Windows
source venv/bin/activate  # macOS/Linux

# Install dependencies
pip install -r requirements.txt

# Run the FastAPI server
uvicorn server.main:app --host 0.0.0.0 --port 8000
```

**Important:** When testing agents locally, always use `./start-app.sh` instead of running uvicorn directly. The start script:
- Loads environment variables from `.env` file (API keys like `ZHIPU_API_KEY`, `ANTHROPIC_API_KEY`)
- Passes these to Docker containers so agents can authenticate
- Handles graceful shutdown of containers on Ctrl+C

### React UI (in ui/ directory)

```bash
cd ui
npm install
npm run dev      # Development server (hot reload)
npm run build    # Production build (required for start-app.sh)
npm run lint     # Run ESLint
```

**Note:** The `start-app.sh` script serves the pre-built UI from `ui/dist/`. After making UI changes, run `npm run build` in the `ui/` directory.

### Docker (Per-Project Containers)

The system uses per-project Docker containers for isolated development:

```bash
# Build the project container image (with SSH key for git clone)
DOCKER_BUILDKIT=1 docker build \
  --secret id=ssh_key,src=$HOME/.ssh/id_ed25519 \
  -f Dockerfile.project -t zerocoder-project .

# Run the test suite (builds, tests containers, cleans up)
./docker-test.sh
```

**Architecture:**
- Host runs FastAPI server + React UI (project management, progress monitoring)
- Each project gets its own Docker container with Claude Code + beads CLI
- Containers are fully standalone - they clone the repo at runtime (no volume mounts)
- SSH key is baked into the image at build time using BuildKit secrets
- Multiple containers can run simultaneously for different projects
- 60-second staggered startup between containers to allow git clone

**Container lifecycle:**
- `not_created` → `running` → `stopped` (15 min idle timeout) → `completed`
- Stopped containers can restart, but will re-fetch latest code from git
- Progress visible via cached data (polled from container every 30s)
- `completed` status when all features are done

**Fresh context per task:**
- Each feature implementation runs in isolated context
- After completing 1 feature + 3 verifications, Claude exits
- System auto-restarts with fresh context for next task
- Continues until all features done or user stops

**Health monitoring:**
- Checks every 5 minutes if agent process is running
- Auto-restarts crashed agents and stopped containers (user-started only)
- Skips containers already in restart process

**Container naming:** `zerocoder-{project-name}-{N}` (e.g., `zerocoder-nexus-1`, `zerocoder-nexus-2`)

### Git Hooks

Pre-commit hooks run unit tests before each commit. To enable:

```bash
./.githooks/setup.sh
# Or manually: git config core.hooksPath .githooks
```

To bypass hooks when needed: `git commit --no-verify`

## Architecture

### Core Python Modules

- `start-app.py` - Web UI backend (FastAPI server launcher)
- `prompts.py` - Prompt template loading with project-specific fallback
- `progress.py` - Progress tracking using beads, webhook notifications
- `registry.py` - Project registry for mapping names to paths (cross-platform)

### Project Registry

Projects are tracked in a SQLite registry:
- **Registry**: `~/.zerocoder/registry.db` (SQLite)
- **Local clones**: `~/.zerocoder/projects/{name}/` (for wizard/edit mode only)

**Container architecture:**
- Containers are fully standalone - they clone repos at runtime
- SSH key is baked into the image at build time (not mounted)
- No volume mounts required - containers are fully isolated

**Key services:**
- `server/services/container_manager.py` - Container lifecycle and agent control
- `server/services/local_project_manager.py` - Local clones for wizard/edit mode
- `registry.py` - Project and container metadata

The registry uses:
- SQLite database with SQLAlchemy ORM
- POSIX path format (forward slashes) for cross-platform compatibility
- SQLite's built-in transaction handling for concurrency safety

### Server API (server/)

The FastAPI server provides REST endpoints for the UI:

- `server/routers/projects.py` - Project CRUD with registry integration
- `server/routers/features.py` - Feature management via container docker exec
- `server/routers/agent.py` - Container control (start/stop/remove)
- `server/routers/spec_creation.py` - WebSocket for interactive spec creation
- `server/services/container_manager.py` - Per-project Docker container lifecycle
- `server/services/container_beads.py` - Send beads commands to containers via docker exec
- `server/services/feature_poller.py` - Background polling service for feature status (30s interval)

### Feature Management

Features are tracked using **beads** (git-backed issue tracking). Each project has its own `.beads/` directory.

**Container-based architecture:**
- All beads operations route through `docker exec` to container scripts
- `container_scripts/beads_commands.py` - Handles CRUD operations inside container
- `container_scripts/feature_status.py` - Returns feature status as JSON
- Feature data cached in SQLite (`FeatureCache`, `FeatureStatsCache` models)
- Background poller updates cache every 30 seconds when container running
- Write operations (create, update, delete, reopen) require container to be running

**Feature data model (beads issues):**
- `id` - String ID (e.g., "beads-1", "beads-2")
- `priority` - P0-P4 (0=critical, 4=backlog)
- `status` - open, in_progress, closed
- `labels` - Category tags
- `title` - Feature name
- `description` - Detailed description with implementation steps

**Agent uses `beads_client` (routes through host API for coordination):**
- `beads_client claim` - Atomically claim next available feature (server-side locking)
- `beads_client stats` - Progress statistics
- `beads_client list --status=open` - List pending features
- `beads_client close <id>` - Mark feature complete
- `beads_client show <id>` - View feature details

### React UI (ui/)

- Tech stack: React 18, TypeScript, TanStack Query, Tailwind CSS v4, Radix UI
- `src/App.tsx` - Main app with project selection, kanban board, agent controls
- `src/hooks/useWebSocket.ts` - Real-time updates via WebSocket
- `src/hooks/useProjects.ts` - React Query hooks for API calls
- `src/lib/api.ts` - REST API client
- `src/lib/types.ts` - TypeScript type definitions
- `src/components/NewProjectModal.tsx` - Multi-step project creation wizard (persists state to `.wizard_status.json`)
- `src/components/IncompleteProjectModal.tsx` - Resume/restart options for interrupted setup
- `src/components/ProjectSelector.tsx` - Project dropdown with incomplete project detection

### Project Structure for Generated Apps

Projects can be stored in any directory (registered in `~/.zerocoder/registry.db`). Each project contains:
- `prompts/app_spec.txt` - Application specification (XML format)
- `prompts/initializer_prompt.md` - First session prompt
- `prompts/coding_prompt.md` - Continuation session prompt
- `prompts/.wizard_status.json` - Wizard state for resuming interrupted setup (deleted on completion)
- `.beads/` - Beads issue tracker for feature management
- `.agent.lock` - Lock file to prevent multiple agent instances

### Security Model

Defense-in-depth approach using Docker containers:
1. Each project runs in isolated Docker container (no volume mounts)
2. Container clones repo fresh at startup - fully isolated filesystem
3. SSH key baked into image at build time (not mounted at runtime)
4. Claude credentials passed via environment variables
5. Non-root `coder` user executes agent code

## Claude Code Integration

- `.claude/commands/create-spec.md` - `/create-spec` slash command for interactive spec creation
- `.claude/skills/frontend-design/SKILL.md` - Skill for distinctive UI design
- `.claude/templates/` - Prompt templates copied to new projects
- `.claude/templates/project_claude.md.template` - CLAUDE.md template with beads workflow instructions
- `.claude/templates/overseer_prompt.template.md` - Unified overseer prompt (adapts to project type)

## Key Patterns

### Prompt Loading Fallback Chain

1. Project-specific: `{project_dir}/prompts/{name}.md`
2. Base template: `.claude/templates/{name}.template.md`

### Agent Session Flow

1. Start project container via UI (creates `zerocoder-{project}` container)
2. Container runs Claude Code with project-specific `CLAUDE.md`
3. Claude implements ONE feature + verifies 3 others, then exits
4. System detects exit, checks for remaining features:
   - If features remain → check for 10% milestone, then auto-restart with fresh context
   - If all done → run final overseer verification, then mark `completed`
5. Health monitor handles crash recovery (every 5 min)

### Overseer Agent

The **Overseer Agent** runs periodic quality verification at 10% completion milestones:

**Trigger Points:**
- At every 10% milestone (10%, 20%, 30%... up to 90%) - runs in parallel with coders
- At 100% completion - final verification before marking project complete

**Verification Tasks:**
1. **Test Suite** - Run all tests, create issues for failures
2. **Spec Verification** (if `app_spec.txt` exists) - Sample 15 features and verify implementations
3. **Code Quality Scan** - Search for TODOs, placeholders, empty functions

**Philosophy:** Better to create a false positive issue than miss a real problem.

**Template:** `.claude/templates/overseer_prompt.template.md` (unified for all project types)

**Key Behaviors:**
- Overseer does NOT implement fixes - only creates/reopens issues
- Uses parallel subagents (3x) for efficient spec verification
- Creates issues aggressively to catch problems early
- Runs in container 0 (`zerocoder-{project}-0`), separate from coding containers

### Real-time UI Updates

The UI receives updates via WebSocket (`/ws/projects/{project_name}`):
- `progress` - Feature pass counts (from `bd stats`)
- `agent_status` - not_created/running/stopped/completed
- `log` - Agent output lines (streamed from `docker logs`)
- `feature_update` - Feature status changes

### Design System

The UI uses a **soft editorial** design with Tailwind CSS v4:
- CSS variables defined in `ui/src/styles/globals.css` via `@theme` directive
- Muted, sophisticated color palette with warm charcoal text
- Soft shadows and refined spacing
- Color tokens: `--color-pending` (amber), `--color-progress` (blue), `--color-done` (green)
