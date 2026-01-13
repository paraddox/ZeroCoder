# ZeroCoder

A long-running autonomous coding agent powered by the Claude Agent SDK. This tool can build complete applications over multiple sessions using a two-agent pattern (initializer + coding agent). Includes a React-based UI for monitoring progress in real-time.

## Prerequisites

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

**Build the project container image:**
```bash
docker build -f Dockerfile.project -t zerocoder-project .
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
1. Creates a container named `zerocoder-{project-name}`
2. Mounts the project directory at `/project`
3. Passes Claude credentials via environment variables
4. Runs Claude Code with beads-based feature tracking

**Container lifecycle:**
- `not_created` → `running` → `stopped` (60 min idle timeout) → `completed`
- Stopped containers persist and restart quickly
- Progress is visible in all states (reads from `.beads/` on host)
- Multiple containers can run simultaneously for different projects
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

Features are tracked using **beads** (git-backed issue tracking). Each project has its own `.beads/` directory. Claude Code uses the `bd` CLI directly via instructions in the project's `CLAUDE.md`:
- `bd stats` - Progress statistics
- `bd ready` - Get available features (no blockers)
- `bd list --status=open` - List pending features
- `bd close <id>` - Mark feature complete
- `bd create` - Create new features

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

```
ZeroCoder/
├── start-app.sh              # Start script (macOS/Linux)
├── start-app.py              # Web UI backend (FastAPI server launcher)
├── autostart.sh              # Enable/disable autostart on system boot
├── Dockerfile.project        # Per-project container image
├── docker-test.sh            # Build and test Docker containers
├── agent_app.py              # Agent SDK app (runs inside containers)
├── progress.py               # Progress tracking utilities
├── prompts.py                # Prompt loading utilities
├── registry.py               # Project registry (SQLite-based)
├── server/
│   ├── main.py               # FastAPI REST API server
│   ├── websocket.py          # WebSocket handler for real-time updates
│   ├── schemas.py            # Pydantic schemas
│   ├── routers/
│   │   ├── projects.py       # Project CRUD with registry integration
│   │   ├── features.py       # Feature management via container docker exec
│   │   ├── agent.py          # Container control (start/stop/remove)
│   │   ├── filesystem.py     # Filesystem browser API
│   │   ├── spec_creation.py  # WebSocket for spec creation wizard
│   │   └── assistant_chat.py # Assistant chat endpoints
│   └── services/
│       ├── container_manager.py     # Per-project Docker container lifecycle
│       ├── container_beads.py       # Send beads commands via docker exec
│       ├── feature_poller.py        # Background feature status polling
│       ├── assistant_chat_session.py # Assistant chat via Agent SDK
│       ├── assistant_database.py    # Assistant chat history storage
│       └── spec_chat_session.py     # Spec creation chat session
├── mcp_server/               # MCP servers for assistant
│   └── issue_creator_mcp.py  # Issue creation tool for assistant
├── container_scripts/        # Scripts that run inside containers
│   ├── feature_status.py     # Returns feature status as JSON
│   └── beads_commands.py     # Beads CRUD operations
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
│       ├── overseer_prompt.template.md
│       └── project_claude.md.template
├── requirements.txt          # Python dependencies
└── .env                      # Optional configuration (N8N webhook)
```

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

1. **Container Isolation:** Each project runs in its own Docker container (`zerocoder-{project-name}`)
2. **Filesystem Restrictions:** Container only has access to the mounted project directory at `/project`
3. **Credential Isolation:** Claude credentials passed via environment variables (not stored in container)
4. **Non-root Execution:** Claude Code runs as a non-root `coder` user inside the container
5. **Permission Mode:** The agent uses `bypassPermissions` mode within the sandboxed container

---

## Web UI Development

The React UI is located in the `ui/` directory.

### Development Mode

```bash
cd ui
npm install
npm run dev      # Development server with hot reload
```

### Building for Production

```bash
cd ui
npm run build    # Builds to ui/dist/
```

**Note:** The `start-app.sh` script serves the pre-built UI from `ui/dist/`. After making UI changes, run `npm run build` to see them when using the start scripts.

### Tech Stack

- React 18 with TypeScript
- TanStack Query for data fetching
- Tailwind CSS v4 with soft editorial design
- Radix UI components
- WebSocket for real-time updates

### Real-time Updates

The UI receives live updates via WebSocket (`/ws/projects/{project_name}`):
- `progress` - Test pass counts
- `agent_status` - Running/paused/stopped/crashed
- `log` - Agent output lines (streamed from subprocess stdout)
- `feature_update` - Feature status changes

---

## Configuration (Optional)

### N8N Webhook Integration

The agent can send progress notifications to an N8N webhook. Create a `.env` file:

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
