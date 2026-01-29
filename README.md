# ZeroCoder

A long-running autonomous coding agent powered by the Claude Agent SDK. This tool can build complete applications over multiple sessions using a two-agent pattern (initializer + coding agent). Includes a React-based UI for monitoring progress in real-time.

## Prerequisites

### Node.js and pnpm (Required)

ZeroCoder requires Node.js 20+ and pnpm package manager:

**Install Node.js:**
Download from https://nodejs.org/ (LTS version recommended)

**Install pnpm:**
```bash
npm install -g pnpm
```

### Claude Code CLI (Required)

This project requires the Claude Code CLI to be installed. Install it using one of these methods:

**macOS / Linux:**
```bash
curl -fsSL https://claude.ai/install.sh | bash
```

**Windows (PowerShell):**
```powershell
irm https://claude.ai/install.ps1 | iex
```

### Authentication

You need one of the following:

- **Claude Pro/Max Subscription** - Use `claude login` to authenticate (recommended)
- **Anthropic API Key** - Pay-per-use from https://console.anthropic.com/
- **Zhipu API Key** - For GLM-4.7 model support (add `ZHIPU_API_KEY` to `.env` file)

### Model Support

ZeroCoder supports multiple AI models:

| Model | SDK | Use Case | API Key |
|-------|-----|----------|---------|
| **GLM-4.7** (default) | OpenCode SDK | Cost-effective coding agent | `ZHIPU_API_KEY` |
| **Claude Sonnet 4.5** | Claude Agent SDK | High-quality coding agent | Claude login or `ANTHROPIC_API_KEY` |
| **Claude Opus 4.5** | Claude Agent SDK | Initializer agent (always) | Claude login or `ANTHROPIC_API_KEY` |

**Note:** The initializer agent (which creates features from your spec) always uses Claude Opus 4.5 for best results. The coding agent uses your configured model (GLM-4.7 by default).

---

## Quick Start

### Web UI

```bash
./start-app.sh
```

This launches the React-based web UI at `http://localhost:8888` (or next available port) with:
- Project selection and creation
- Kanban board view of features
- Real-time agent output streaming
- Start/stop controls for per-project Docker containers

### Autostart on Boot (Linux)

To have ZeroCoder start automatically when your system boots:

```bash
./autostart.sh          # Enable autostart
./autostart.sh --remove # Disable autostart
```

Once enabled, you can manage the service with:
```bash
systemctl --user start zerocoder   # Start now
systemctl --user stop zerocoder    # Stop
systemctl --user status zerocoder  # Check status
journalctl --user -u zerocoder -f  # View logs
```

### Creating or Continuing a Project

In the web UI you can:
- **Create new project** - Start a fresh project with AI-assisted spec generation
- **Add existing repository** - Add an existing codebase with its own CLAUDE.md and skills
- **Continue existing project** - Resume work on a previous project

For new projects, use the built-in spec creation wizard to interactively create your app specification with Claude's help.

**Adding Existing Repos:** You can add any existing repository to ZeroCoder. The system preserves your existing CLAUDE.md, skills, and project structure while initializing beads issue tracking. This lets you use ZeroCoder's feature management with codebases that already have Claude Code configuration.

**Interrupted Setup:** If you close the browser during project setup (before completing the spec), you can resume where you left off. Incomplete projects show a warning icon in the project selector.

### Assistant Chat

Each project includes an AI assistant that can help you:
- Explore and understand the codebase
- Answer questions about the project
- Create new features/issues interactively

The assistant uses read-only tools (can't modify code) but can create issues via the same mechanism as the UI. Click the chat icon in the bottom-right corner when a project is selected.

**Note:** The assistant is only available when the agent is not running (or container is in edit mode).

### Docker (Per-Project Containers)

ZeroCoder uses a per-project container architecture for isolated, sandboxed development:

- **Host runs:** FastAPI server + React UI (project management, progress monitoring)
- **Each project gets:** Its own Docker container with Claude Code + beads CLI
- **Benefits:** Multiple projects can run simultaneously, each fully isolated

**Build the project container image (with SSH key for git clone):**
```bash
DOCKER_BUILDKIT=1 docker build \
  --secret id=ssh_key,src=$HOME/.ssh/id_ed25519 \
  -f Dockerfile.project -t zerocoder-project .
```

**Run the test suite:**
```bash
./docker-test.sh
```

This builds the image, starts the server, creates test projects, spins up containers, and verifies everything works.

**Start the UI:**
```bash
./start-app.sh
```

When you start an agent for a project via the UI, it automatically:
1. Creates a container named `zerocoder-{project-name}-{N}` (N = container number)
2. Clones the project repository fresh from git (no volume mounts)
3. Passes Claude credentials via environment variables
4. Runs Claude Code with beads-based feature tracking

**Note:** Multiple containers can run simultaneously for the same project (e.g., `zerocoder-nexus-1`, `zerocoder-nexus-2`). Each claims different features via atomic locking through the host API.

**Container lifecycle:**
- `not_created` → `running` → `stopped` (15 min idle timeout) → `completed`
- Containers clone repos fresh at startup (fully standalone, no volume mounts)
- SSH key is baked into image at build time using BuildKit secrets
- Progress synced via host API (beads operations route through server)
- Multiple containers can run simultaneously with 60-second staggered startup
- `completed` status when all features are done

**Fresh context per task:**
- Each feature implementation runs in isolated context window
- After completing 1 feature + 3 verifications, Claude exits
- System auto-restarts with fresh context for the next task
- Continues automatically until all features done or user stops
- Health monitor auto-recovers crashed agents (every 10 min)

---

## How It Works

### Two-Agent Pattern

1. **Initializer Agent (First Session):** Reads your app specification, creates features using beads issue tracking (`.beads/` directory), sets up the project structure, and initializes git.

2. **Coding Agent (Subsequent Sessions):** Each session runs with fresh context:
   - Implements ONE feature (marks `in_progress` → `closed`)
   - Verifies 3 previously completed features
   - Exits cleanly after one task cycle
   - System auto-restarts for next feature

### Feature Management

Features are tracked using **beads** (git-backed issue tracking). Each project has its own `.beads/` directory. Agents use `beads_client` which routes through the host API for coordination:
- `beads_client claim` - Atomically claim next available feature (server-side locking)
- `beads_client stats` - Progress statistics
- `beads_client list --status=open` - List pending features
- `beads_client close <id>` - Mark feature complete
- `beads_client show <id>` - View feature details

This architecture enables multiple containers to work on the same project without conflicts.

### Session Management

- **Fresh context per task:** Each feature runs in isolated context window
- Progress is persisted via beads (`.beads/` directory) and git commits
- Auto-restart: System immediately starts new session after each task
- Auto-completion: Stops automatically when all features are done
- Health monitor: Recovers crashed agents every 10 minutes
- Use UI controls to stop/start agent manually

---

## Important Timing Expectations

> **Note: Building complete applications takes time!**

- **First session (initialization):** The agent generates feature test cases. This takes several minutes and may appear to hang - this is normal.

- **Subsequent sessions:** Each coding iteration can take **5-15 minutes** depending on complexity.

- **Full app:** Building all features typically requires **many hours** of total runtime across multiple sessions.

**Tip:** The feature count in the prompts determines scope. For faster demos, you can modify your app spec to target fewer features (e.g., 20-50 features for a quick demo).

---

## Project Structure

ZeroCoder is organized as a pnpm monorepo with TypeScript backend:

```
ZeroCoder/
├── start-app.sh              # Start script (macOS/Linux)
├── package.json              # Root monorepo configuration
├── pnpm-workspace.yaml       # Workspace definition
├── autostart.sh              # Enable/disable autostart on system boot
├── Dockerfile.project        # Per-project container image
├── docker-test.sh            # Build and test Docker containers
├── agent_app.py              # Claude Agent SDK app (runs inside containers)
├── opencode_agent_app.ts     # OpenCode SDK agent for GLM-4.7 (TypeScript)
├── packages/                 # Monorepo packages
│   ├── server/               # TypeScript backend (@zerocoder/server)
│   │   ├── src/
│   │   │   ├── index.ts      # Hono server entry point
│   │   │   ├── app.ts        # App configuration with middleware
│   │   │   ├── routers/      # API route handlers
│   │   │   │   ├── projects.ts
│   │   │   │   ├── features.ts
│   │   │   │   ├── agent.ts
│   │   │   │   ├── assistant.ts
│   │   │   │   ├── beads-api.ts
│   │   │   │   ├── spec-creation.ts
│   │   │   │   └── remote-machines.ts
│   │   │   ├── services/     # Business logic
│   │   │   │   ├── container-manager.ts
│   │   │   │   ├── beads-manager.ts
│   │   │   │   ├── local-project-manager.ts
│   │   │   │   ├── assistant-database.ts
│   │   │   │   └── assistant-chat-session.ts
│   │   │   ├── db/           # Database layer (Drizzle ORM)
│   │   │   │   ├── schema.ts
│   │   │   │   ├── crud.ts
│   │   │   │   └── assistant-db.ts
│   │   │   ├── websocket/    # WebSocket handlers
│   │   │   │   ├── index.ts
│   │   │   │   ├── connection-manager.ts
│   │   │   │   └── callback-system.ts
│   │   │   └── utils/        # Shared utilities
│   │   ├── package.json
│   │   └── tsconfig.json
│   └── shared/               # Shared types (@zerocoder/shared)
│       ├── src/
│       │   ├── types.ts      # TypeScript type definitions
│       │   └── schemas.ts    # Zod validation schemas
│       ├── package.json
│       └── tsconfig.json
├── mcp_server/               # MCP servers for assistant
│   └── issue_creator_mcp.py  # Issue creation tool for assistant
├── container_scripts/        # Scripts that run inside containers
│   ├── beads_client.sh       # Routes beads commands through host API
│   ├── beads_commands.py     # Beads CRUD operations
│   ├── feature_status.py     # Returns feature status as JSON
│   └── setup_repo.sh         # Repository setup after clone
├── ui/                       # React frontend
│   ├── src/
│   │   ├── App.tsx           # Main app component
│   │   ├── components/       # 25 React components (Kanban, modals, etc.)
│   │   ├── hooks/            # Custom hooks (WebSocket, theme, sounds)
│   │   ├── lib/              # API client and types
│   │   └── styles/           # Tailwind CSS globals
│   ├── package.json
│   └── vite.config.ts
├── .claude/
│   ├── commands/
│   │   ├── create-spec.md    # /create-spec slash command
│   │   └── checkpoint.md     # /checkpoint for saving progress
│   ├── skills/
│   │   └── frontend-design/  # Distinctive UI design skill
│   └── templates/            # Prompt templates for agents
│       ├── initializer_prompt.template.md
│       ├── coding_prompt.template.md
│       └── project_claude.md.template
└── .env                      # Optional configuration (API keys, webhooks)
```

### Backend Technology Stack

| Component | Technology |
|-----------|------------|
| Framework | [Hono](https://hono.dev/) - Fast, lightweight web framework |
| ORM | [Drizzle ORM](https://orm.drizzle.team/) - Type-safe SQL-like ORM |
| Database | SQLite (better-sqlite3) |
| Validation | [Zod](https://zod.dev/) - TypeScript-first validation |
| WebSocket | ws library |
| Testing | Vitest |
| Build | TypeScript compiler |

---

## Generated Project Structure

After the agent runs, your project directory will contain:

```
my_project/
├── .beads/                   # Beads issue tracking (git-backed)
├── CLAUDE.md                 # Instructions for Claude Code
├── prompts/
│   ├── app_spec.txt          # Your app specification
│   ├── initializer_prompt.md # First session prompt
│   └── coding_prompt.md      # Continuation session prompt
├── init.sh                   # Environment setup script
└── [application files]       # Generated application code
```

---

## Running the Generated Application

After the agent completes (or pauses), you can run the generated application:

```bash
cd /path/to/your/project

# Run the setup script created by the agent
./init.sh

# Or manually (typical for Node.js apps):
npm install
npm run dev
```

The application will typically be available at `http://localhost:3000` or similar.

**Note:** Projects are stored in their registered locations (any directory you choose when creating the project), not in a fixed `generations/` folder.

---

## Security Model

This project uses Docker container isolation for security:

1. **Container Isolation:** Each project runs in its own Docker container (`zerocoder-{project}-{N}`)
2. **Standalone Containers:** Containers clone repos fresh at startup - no volume mounts to host filesystem
3. **SSH Key Security:** SSH key baked into image at build time via BuildKit secrets (not in image layers)
4. **Credential Isolation:** Claude credentials passed via environment variables (not stored in container)
5. **Non-root Execution:** Claude Code runs as a non-root `coder` user inside the container
6. **Permission Mode:** The agent uses `bypassPermissions` mode within the sandboxed container

---

## Development Workflow

### Monorepo Commands

From the root directory:

```bash
# Install all dependencies
pnpm install

# Development mode (runs server and UI in parallel)
pnpm run dev

# Or run individually:
pnpm run dev:server    # Server only (hot reload)
pnpm run dev:ui        # UI only (Vite dev server)

# Build all packages
pnpm run build

# Run tests
pnpm run test          # Run all tests in watch mode
pnpm run test:run      # Run tests once (for CI)

# Type checking
pnpm run typecheck     # Check all packages
```

### Web UI Development

The React UI is located in the `ui/` directory.

```bash
cd ui
pnpm install
pnpm run dev      # Development server with hot reload
pnpm run build    # Production build
```

**Note:** The `start-app.sh` script serves the pre-built UI from `ui/dist/`. After making UI changes, run `pnpm run build` to see them when using the start scripts.

### Tech Stack

- **Backend:** TypeScript, Hono, Drizzle ORM, SQLite, Zod
- **Frontend:** React 18, TypeScript, TanStack Query, Tailwind CSS v4, Radix UI
- **Testing:** Vitest
- **Package Manager:** pnpm
- **WebSocket:** Real-time updates for agent status and logs

### Real-time Updates

The UI receives live updates via WebSocket (`/ws/projects/{project_name}`):
- `progress` - Test pass counts
- `agent_status` - Running/paused/stopped/crashed
- `log` - Agent output lines (streamed from subprocess stdout)
- `feature_update` - Feature status changes

---

## Configuration (Optional)

### API Keys

Create a `.env` file in the project root with your API keys:

```bash
# For GLM-4.7 model (default)
ZHIPU_API_KEY=your_zhipu_api_key_here

# For Claude models (if not using claude login)
ANTHROPIC_API_KEY=your_anthropic_api_key_here
```

**Important:** Always use `./start-app.sh` to start the server. It:
- Loads the `.env` file and passes API keys to Docker containers
- Installs dependencies via pnpm
- Builds the TypeScript server
- Builds the Docker image with your SSH key

### Changing the Agent Model

Each project stores its model configuration in `prompts/.agent_config.json`:

```json
{
  "agent_model": "glm-4-7"
}
```

Supported values:
- `glm-4-7` - GLM-4.7 via OpenCode SDK (default, cost-effective)
- `claude-sonnet-4-5-20250514` - Claude Sonnet 4.5 via Claude Agent SDK

### N8N Webhook Integration

The agent can send progress notifications to an N8N webhook. Add to your `.env` file:

```bash
# Optional: N8N webhook for progress notifications
PROGRESS_N8N_WEBHOOK_URL=https://your-n8n-instance.com/webhook/your-webhook-id
```

When test progress increases, the agent sends:

```json
{
  "event": "test_progress",
  "passing": 45,
  "total": 200,
  "percentage": 22.5,
  "project": "my_project",
  "timestamp": "2025-01-15T14:30:00.000Z"
}
```

---

## Customization

### Changing the Application

Use the `/create-spec` command when creating a new project, or manually edit the files in your project's `prompts/` directory:
- `app_spec.txt` - Your application specification
- `initializer_prompt.md` - Controls feature generation

### Modifying Container Behavior

Edit `Dockerfile.project` to customize the container environment (installed packages, tools, etc.).

---

## Troubleshooting

**"Claude CLI not found"**
Install the Claude Code CLI using the instructions in the Prerequisites section.

**"Not authenticated with Claude"**
Run `claude login` to authenticate. The start script will prompt you to do this automatically.

**"Appears to hang on first run"**
This is normal. The initializer agent is generating detailed test cases, which takes significant time. Watch for `[Tool: ...]` output to confirm the agent is working.

**"Container permission denied"**
The Docker container runs as a non-root `coder` user for security. If you encounter permission issues, ensure the project directory has appropriate permissions for the container to read/write files.

---



## License

MIT License
