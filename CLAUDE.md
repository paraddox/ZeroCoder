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
# Create and activate virtual hhh
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
# Build the project container image
docker build -f Dockerfile.project -t zerocoder-project .

# Run the test suite (builds, tests containers, cleans up)
./docker-test.sh
```

**Architecture:**
- Host runs FastAPI server + React UI (project management, progress monitoring)
- Each project gets its own Docker container with Claude Code + beads CLI
- Multiple containers can run simultaneously for different projects

**Container lifecycle:**
- `not_created` → `running` → `stopped` (15 min idle timeout) → `completed`
- Stopped containers persist and restart quickly
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

**Container naming:** `zerocoder-{project-name}`

## Architecture

### Core Python Modules

- `start-app.py` - Web UI backend (FastAPI server launcher)
- `prompts.py` - Prompt template loading with project-specific fallback
- `progress.py` - Progress tracking using beads, webhook notifications
- `registry.py` - Project registry for mapping names to paths (cross-platform)

### Project Registry

Projects can be stored in any directory. The registry maps project names to paths using SQLite:
- **All platforms**: `~/.zerocoder/registry.db`

The registry uses:
- SQLite database with SQLAlchemy ORM
- POSIX path format (forward slashes) for cross-platform compatibility
- SQLite's built-in transaction handling for concurrency safety

### Server API (server/)

The FastAPI server provides REST endpoints for the UI:

- `server/routers/projects.py` - Project CRUD with registry integration
- `server/routers/features.py` - Feature management via container docker exec
- `server/routers/agent.py` - Container control (start/stop/remove)
- `server/routers/filesystem.py` - Filesystem browser API with security controls
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

**Agent uses beads CLI directly:**
- `bd stats` - Progress statistics
- `bd ready` - Get available features (no blockers)
- `bd list --status=open` - List pending features
- `bd close <id>` - Mark feature complete
- `bd create` - Create new features

### React UI (ui/)

- Tech stack: React 18, TypeScript, TanStack Query, Tailwind CSS v4, Radix UI
- `src/App.tsx` - Main app with project selection, kanban board, agent controls
- `src/hooks/useWebSocket.ts` - Real-time updates via WebSocket
- `src/hooks/useProjects.ts` - React Query hooks for API calls
- `src/lib/api.ts` - REST API client
- `src/lib/types.ts` - TypeScript type definitions
- `src/components/FolderBrowser.tsx` - Server-side filesystem browser for project folder selection
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
1. Each project runs in isolated Docker container
2. Container filesystem limited to mounted project directory
3. Claude credentials passed via environment variables

## Claude Code Integration

- `.claude/commands/create-spec.md` - `/create-spec` slash command for interactive spec creation
- `.claude/skills/frontend-design/SKILL.md` - Skill for distinctive UI design
- `.claude/templates/` - Prompt templates copied to new projects
- `.claude/templates/project_claude.md.template` - CLAUDE.md template with beads workflow instructions

## Key Patterns

### Prompt Loading Fallback Chain

1. Project-specific: `{project_dir}/prompts/{name}.md`
2. Base template: `.claude/templates/{name}.template.md`

### Agent Session Flow

1. Start project container via UI (creates `zerocoder-{project}` container)
2. Container runs Claude Code with project-specific `CLAUDE.md`
3. Claude implements ONE feature + verifies 3 others, then exits
4. System detects exit, checks for remaining features:
   - If features remain → auto-restart with fresh context
   - If all done → mark `completed`, stop container
5. Health monitor handles crash recovery (every 10 min)

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
