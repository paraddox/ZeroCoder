# OpenCode SDK Reference Documentation

Compiled from Context7 MCP - January 2026

## Overview

The OpenCode SDK provides TypeScript/JavaScript access to the OpenCode REST API for building AI coding agents. It supports server-side usage, streaming responses, and detailed error handling.

**Library ID:** `/sst/opencode-sdk-js` (SDK JS), `/anomalyco/opencode` (OpenCode Core)

---

## Client Initialization

```typescript
import Opencode from '@opencode-ai/sdk';
import { createOpencode } from "@opencode-ai/sdk";

// Basic client
const client = new Opencode();

// With custom logging
import pino from 'pino';
const logger = pino({ level: 'debug' });
const client = new Opencode({
  logger: logger.child({ name: 'Opencode' }),
  logLevel: 'debug'  // 'debug' | 'info' | 'warn' | 'error' | 'off'
});

// With retries and timeout
const client = new Opencode({
  maxRetries: 5,
  timeout: 60000 // 1 minute
});

// Using createOpencode (starts local server)
const opencode = await createOpencode({ port: 5000 });
const client = opencode.client;
// Don't forget: opencode.server.close() when done
```

---

## Session Management

### Create Session
```typescript
const session = await client.session.create();
console.log(`Session created: ${session.id}`);
```

### List Sessions
```typescript
const sessions = await client.session.list();
sessions.forEach(s => {
  console.log(`Session ${s.id}: ${s.time.created}`);
});
```

### Send Message (Synchronous)
```typescript
const response = await client.session.chat(sessionId, {
  parts: [
    { type: 'text', text: 'Analyze this code' },
    { type: 'file', source: { type: 'path', path: './src/main.ts' } }
  ]
});
```

### Send Message (Asynchronous)
```typescript
await client.session.promptAsync({
  path: { id: sessionId },
  body: {
    parts: [{ type: "text", text: prompt }],
  },
});
```

### Abort Session
```typescript
await client.session.abort(sessionId);
// or with path format:
await client.session.abort({ path: { id: sessionId } });
```

### Delete Session
```typescript
await client.session.delete(sessionId);
```

---

## Event Streaming (SSE)

### Stream All Events
```typescript
const stream = await client.event.list();

for await (const event of stream) {
  switch (event.type) {
    case 'message.updated':
      console.log('New message:', event.properties.info);
      break;
    case 'file.edited':
      console.log('File changed:', event.properties.file);
      break;
    case 'session.updated':
      console.log('Session updated:', event.properties.info);
      break;
    case 'session.error':
      console.error('Session error:', event.properties.error);
      break;
    case 'file.watcher.updated':
      console.log('File watch event:', event.properties.event, event.properties.file);
      break;
    default:
      console.log('Event:', event.type);
  }
}

// Cancel the stream
stream.controller.abort();
```

### Subscribe with Global Event Handler
```typescript
const eventResult = await client.global.event({
  onSseEvent: (event) => {
    const payload = event?.data?.payload || event?.payload;
    if (!payload) return;

    const eventType = payload.type;
    const props = payload.properties;

    switch (eventType) {
      case "message.part.updated":
        // Text streaming delta
        if (props?.delta) {
          process.stdout.write(props.delta);
        }
        // Tool invocation
        if (props?.part?.type === "tool-invocation" || props?.part?.type === "tool_use") {
          console.log(`Tool: ${props.part?.name || props.part?.toolName}`);
        }
        break;

      case "session.idle":
        console.log("Session completed");
        break;

      case "session.error":
        console.error("Error:", props?.error);
        break;

      case "file.edited":
        console.log(`Edited: ${props?.file}`);
        break;

      case "todo.updated":
        console.log(`Todo: ${props?.todo?.content}`);
        break;
    }
  },
  onSseError: (error) => {
    console.error('SSE error:', error?.message);
  },
});

// Cancel when done
eventResult.cancel();
```

### Filter Events by Session and Type
```typescript
import { createOpencodeClient } from "@opencode-ai/sdk"

const client = createOpencodeClient({ baseUrl: "http://localhost:4096" })

const eventStream = client.global.event.get({
  query: {
    session: ["session-id-here"],
    event: [
      "session.updated",
      "session.diff",
      "session.error",
      "message.created",
      "permission.asked"
    ]
  }
})

for await (const event of eventStream) {
  // Process filtered events
}
```

---

## Available Event Types

| Event Type | Description | Properties |
|------------|-------------|------------|
| `message.updated` | Message content updated | `info` |
| `message.part.updated` | Streaming text delta | `delta`, `part` |
| `message.created` | New message created | `role`, `parts` |
| `session.updated` | Session state changed | `id`, `title` |
| `session.idle` | Session completed | - |
| `session.error` | Session error occurred | `error` |
| `session.diff` | Files modified | `files`, `additions`, `deletions`, `diffs` |
| `file.edited` | File was edited | `file` |
| `file.watcher.updated` | File watch event | `event`, `file` |
| `todo.updated` | Todo item updated | `todo.content` |
| `permission.asked` | Permission requested | `permission`, `pattern`, `message` |

---

## Thinking Mode Configuration

### For Anthropic Models (Claude)
```jsonc
// opencode.json
{
  "$schema": "https://opencode.ai/config.json",
  "provider": {
    "anthropic": {
      "models": {
        "claude-sonnet-4-5-20250929": {
          "options": {
            "thinking": {
              "type": "enabled",
              "budgetTokens": 16000
            }
          }
        }
      }
    }
  }
}
```

### For OpenAI/Reasoning Models
```jsonc
// opencode.json
{
  "$schema": "https://opencode.ai/config.json",
  "provider": {
    "openai": {
      "models": {
        "gpt-5": {
          "options": {
            "reasoningEffort": "high",
            "textVerbosity": "low",
            "reasoningSummary": "auto",
            "include": ["reasoning.encrypted_content"]
          }
        }
      }
    }
  }
}
```

### Model Variants with Thinking
```jsonc
{
  "$schema": "https://opencode.ai/config.json",
  "provider": {
    "openai": {
      "models": {
        "gpt-5": {
          "variants": {
            "thinking": {
              "reasoningEffort": "high",
              "textVerbosity": "low"
            },
            "fast": {
              "disabled": true
            }
          }
        }
      }
    }
  }
}
```

### Agent-Level Configuration
```json
{
  "agent": {
    "deep-thinker": {
      "description": "Agent that uses high reasoning effort for complex problems",
      "model": "openai/gpt-5",
      "reasoningEffort": "high",
      "textVerbosity": "low"
    }
  }
}
```

---

## GLM Model Support

OpenCode's Zen API supports GLM models via OpenAI-compatible endpoint:

**Endpoint:** `POST /zen/v1/chat/completions`

**Supported Models:** GLM, Kimi, Qwen, Grok, Big Pickle

```json
{
  "model": "glm-4.6",
  "messages": [
    {"role": "system", "content": "You are a helpful assistant."},
    {"role": "user", "content": "Write a short poem about the sea."}
  ],
  "max_tokens": 100,
  "temperature": 0.8
}
```

---

## App Configuration

### Get App Info
```typescript
const app = await client.app.get();
console.log(`Hostname: ${app.hostname}`);
console.log(`CWD: ${app.path.cwd}`);
console.log(`Config path: ${app.path.config}`);
console.log(`Git repository: ${app.git}`);
```

### List Providers
```typescript
const providers = await client.app.providers();
providers.forEach(provider => {
  console.log(`Provider: ${provider.id}`);
  provider.models.forEach(model => {
    console.log(`  - ${model.id} (cost: $${model.cost.input}/$${model.cost.output} per token)`);
  });
});
```

### List Modes
```typescript
const modes = await client.app.modes();
modes.forEach(mode => {
  console.log(`Mode: ${mode.name}`);
  console.log(`  Tools:`, Object.keys(mode.tools).filter(t => mode.tools[t]));
  if (mode.model) {
    console.log(`  Model: ${mode.model.providerID}/${mode.model.modelID}`);
  }
});
```

---

## Plugin Development

Plugins can hook into various events:

```typescript
import type { Plugin } from "@opencode-ai/plugin"
import { tool } from "@opencode-ai/plugin"

export const MyPlugin: Plugin = async (input) => {
  return {
    // Before tool execution
    async "tool.execute.before"(input, output) {
      const { tool, args } = input
      console.log(`Executing tool: ${tool}`, args)
    },

    // After tool execution
    async "tool.execute.after"(input, output) {
      const { tool, result } = input
      // Track tool usage
    },

    // Handle server events
    async event(event) {
      if (event.type === "session.created") {
        console.log("New session:", event.properties.id)
      }
    }
  }
}
```

### Plugin Event Categories
- **Command Events:** `command.executed`
- **File Events:** `file.edited`
- **Installation Events:** `installation.updated`
- **LSP Events:** `lsp.client.diagnostics`
- **Message Events:** `message.updated`, `message.created`
- **Permission Events:** `permission.asked`
- **Session Events:** `session.updated`, `session.idle`, `session.error`
- **Todo Events:** `todo.updated`
- **Tool Events:** `tool.execute.before`, `tool.execute.after`

---

## Error Handling

```typescript
try {
  const session = await client.session.create();
} catch (err) {
  if (err && typeof err === 'object' && 'status' in err) {
    const apiErr = err as { status?: number; message?: string };

    if (apiErr.status === 401) {
      console.error("Authentication failed");
    } else if (apiErr.status === 429) {
      console.error("Rate limited");
    }
  }
}
```

---

## Environment Variables

| Variable | Description |
|----------|-------------|
| `OPENCODE_LOG` | Set logging level: `debug`, `info`, `warn`, `error`, `off` |
| `ZHIPU_API_KEY` | API key for GLM models |

---

## References

- OpenCode SDK JS: https://github.com/sst/opencode-sdk-js
- OpenCode Core: https://github.com/anomalyco/opencode
- Documentation: https://opencode.ai/docs
