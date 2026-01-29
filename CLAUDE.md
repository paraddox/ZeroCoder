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

### TypeScript Backend (Monorepo)

ZeroCoder uses a pnpm monorepo structure with TypeScript:

```bash
# Install dependencies (run from root)
pnpm install

# Development mode (hot reload)
pnpm run dev:server    # Start server in dev mode
pnpm run dev:ui        # Start UI dev server

# Build for production
pnpm run build:server  # Build server package
pnpm run build:ui      # Build UI package

# Run tests
pnpm run test          # Run all tests
pnpm run test:run      # Run tests once (CI)

# Type checking
pnpm run typecheck     # Check all packages
```

**Important:** When testing agents locally, always use `./start-app.sh` instead of running the server directly. The start script:
- Loads environment variables from `.env` file (API keys like `ZHIPU_API_KEY`, `ANTHROPIC_API_KEY`)
- Passes these to Docker containers so agents can authenticate
- Handles graceful shutdown of containers on Ctrl+C
- Installs dependencies and builds packages automatically

### React UI (in ui/ directory)

The UI is located in the `ui/` directory and uses pnpm:

```bash
cd ui
pnpm install
pnpm run dev      # Development server (hot reload)
pnpm run build    # Production build (required for start-app.sh)
pnpm run lint     # Run ESLint
```

**Note:** The `start-app.sh` script serves the pre-built UI from `ui/dist/`. After making UI changes, run `pnpm run build` in the `ui/` directory.

### Docker (Per-Project Containers)

The system uses per-project Docker containers for isolated development:

```bash
# Build the project container image (with SSH key for git clone)
# SSH key path can be configured via GIT_SSH_KEY_PATH in .env file
DOCKER_BUILDKIT=1 docker build \
  --secret id=ssh_key,src=${GIT_SSH_KEY_PATH:-$HOME/.ssh/id_ed25519} \
  -f Dockerfile.project -t zerocoder-project .

# Run the test suite (builds, tests containers, cleans up)
./docker-test.sh
```

**Architecture:**
- Host runs FastAPI server + React UI (project management, progress monitoring)
- Each project gets its own Docker container with Claude Code + beads CLI
- Containers are fully standalone - they clone the repo at runtime (no volume mounts)
- SSH key is baked into the image at build time using BuildKit secrets (configure path via `GIT_SSH_KEY_PATH` in `.env`)
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

## Development Rules

### Pre-Commit Hooks
- **NEVER skip pre-commit hooks** with `--no-verify`
- All commits MUST pass pre-commit tests
- If tests fail, fix them before committing

## Architecture

### Monorepo Structure

ZeroCoder is organized as a pnpm monorepo with three main packages:

```
ZeroCoder/
├── package.json                 # Root monorepo configuration
├── pnpm-workspace.yaml          # Workspace definition
├── packages/
│   ├── server/                  # TypeScript backend (@zerocoder/server)
│   │   ├── src/
│   │   │   ├── index.ts         # Server entry point
│   │   │   ├── app.ts           # Hono app configuration
│   │   │   ├── routers/         # API route handlers
│   │   │   ├── services/        # Business logic
│   │   │   ├── db/              # Database schema & CRUD
│   │   │   ├── middleware/      # Express/Hono middleware
│   │   │   ├── websocket/       # WebSocket handlers
│   │   │   └── utils/           # Shared utilities
│   │   └── package.json
│   └── shared/                  # Shared types (@zerocoder/shared)
│       ├── src/
│       │   ├── types.ts         # TypeScript type definitions
│       │   └── schemas.ts       # Zod validation schemas
│       └── package.json
└── ui/                          # React frontend
    └── package.json
```

### Core Modules (TypeScript)

- `packages/server/src/index.ts` - Hono server entry point
- `packages/server/src/app.ts` - App configuration with middleware
- `packages/server/src/services/` - Business logic services
  - `container-manager.ts` - Docker container lifecycle
  - `beads-manager.ts` - Beads issue tracking operations
  - `local-project-manager.ts` - Local project management
  - `assistant-database.ts` - Assistant chat history storage
- `packages/server/src/routers/` - API route handlers
  - `projects.ts` - Project CRUD operations
  - `features.ts` - Feature management
  - `agent.ts` - Container/agent control
  - `assistant.ts` - Assistant chat endpoints
  - `spec-creation.ts` - Spec creation wizard
- `packages/server/src/db/` - Database layer
  - `schema.ts` - Drizzle ORM schema definitions
  - `crud.ts` - Database CRUD operations
  - `assistant-db.ts` - Assistant chat storage
- `packages/shared/src/` - Shared package
  - `types.ts` - TypeScript type definitions
  - `schemas.ts` - Zod validation schemas

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

### Server API (packages/server/)

The TypeScript server uses Hono framework and provides REST endpoints for the UI:

**Routers:**
- `routers/projects.ts` - Project CRUD with registry integration
- `routers/features.ts` - Feature management via container docker exec
- `routers/agent.ts` - Container control (start/stop/remove)
- `routers/spec-creation.ts` - WebSocket for interactive spec creation
- `routers/assistant.ts` - Assistant chat endpoints
- `routers/beads-api.ts` - Beads operations API

**Services:**
- `services/container-manager.ts` - Per-project Docker container lifecycle
- `services/beads-manager.ts` - Beads commands and operations
- `services/local-project-manager.ts` - Local project management
- `services/assistant-database.ts` - Assistant chat history storage
- `services/task-cleanup.ts` - Background task cleanup
- `services/branch-cleanup.ts` - Branch cleanup service

**Database:**
- `db/schema.ts` - Drizzle ORM schema (SQLite)
- `db/crud.ts` - Database CRUD operations
- `db/assistant-db.ts` - Assistant-specific database operations

**WebSocket:**
- `websocket/index.ts` - WebSocket server setup
- `websocket/connection-manager.ts` - Connection management
- `websocket/callback-system.ts` - Callback handling for async operations

**Key Technologies:**
- Hono - Fast, lightweight web framework
- Drizzle ORM - Type-safe SQL-like ORM
- Zod - Runtime type validation
- Better-sqlite3 - SQLite database driver

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
