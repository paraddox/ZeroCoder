---
name: hound
description: Periodic code review of closed tasks
model: zhipu/glm-4.7
temperature: 0.2
prompt: |
  {file:/project/CLAUDE.md}

  {file:/project/prompts/hound_prompt.md}
tools:
  read: true
  write: true
  edit: true
  bash: true
---
