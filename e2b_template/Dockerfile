# =============================================================================
# E2B Sandbox Template Dockerfile
# =============================================================================
# Custom sandbox environment for running Claude Agent SDK in E2B cloud.
#
# This template provides:
# - Python 3.11 + claude-agent-sdk
# - Node.js 22 + Claude Code CLI
# - Git with SSH support
# - Development tools (curl, jq, build-essential, etc.)
#
# Key differences from Docker containers:
# - SSH key passed via environment variable (base64 encoded)
# - Host API accessible via public URL (no host.docker.internal)
# - E2B manages sandbox lifecycle (no custom entrypoint)

FROM python:3.11-slim-bookworm

# Prevent interactive prompts
ENV DEBIAN_FRONTEND=noninteractive

# Disable beads daemon in sandboxes (avoids stale lock file issues)
ENV BD_NO_DAEMON=true
ENV BEADS_AUTO_START_DAEMON=false

# Install essentials and development tools
RUN apt-get update && apt-get install -y \
    git \
    curl \
    wget \
    ca-certificates \
    sudo \
    procps \
    jq \
    tree \
    zip \
    unzip \
    rsync \
    build-essential \
    openssh-client \
    && rm -rf /var/lib/apt/lists/*

# Install Node.js v22 (required for Claude Code CLI)
RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Install pnpm and yarn globally
RUN npm install -g pnpm yarn

# Install Claude Code CLI globally (required by Agent SDK)
RUN npm install -g @anthropic-ai/claude-code

# Install Claude Agent SDK
RUN pip install --no-cache-dir claude-agent-sdk requests

# =============================================================================
# SSH Setup (key decoded at runtime from environment variable)
# =============================================================================
# SSH key is passed as SSH_PRIVATE_KEY_BASE64 environment variable
# and decoded at sandbox startup by setup_sandbox.sh

# Create .ssh directory with correct permissions
RUN mkdir -p /root/.ssh && chmod 700 /root/.ssh

# Add GitHub to known_hosts (prevents "authenticity" prompts)
RUN ssh-keyscan github.com >> /root/.ssh/known_hosts 2>/dev/null \
    && chmod 644 /root/.ssh/known_hosts

# =============================================================================
# Agent Scripts
# =============================================================================

# Create app directory for scripts
RUN mkdir -p /app

# Copy agent application and scripts
COPY agent_app.py /app/agent_app.py
COPY beads_commands.py /app/beads_commands.py
COPY beads_client.sh /app/beads_client.sh
COPY setup_sandbox.sh /app/setup_sandbox.sh

# Make scripts executable
RUN chmod +x /app/beads_client.sh /app/setup_sandbox.sh

# Create symlinks for beads_client so agents can call it easily
RUN ln -s /app/beads_client.sh /usr/local/bin/beads_client \
    && ln -s /app/beads_client.sh /usr/local/bin/bd

# Configure git for agent operations
RUN git config --global user.email "agent@zerocoder.local" \
    && git config --global user.name "ZeroCoder Agent" \
    && git config --global init.defaultBranch main

# Create project directory
RUN mkdir -p /project
WORKDIR /project

# Default shell
CMD ["/bin/bash"]
