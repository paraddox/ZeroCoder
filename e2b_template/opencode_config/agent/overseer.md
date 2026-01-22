---
name: overseer
description: Verifies all features are properly implemented
model: zhipu/glm-4.7
temperature: 0.2
prompt: |
  {file:/project/CLAUDE.md}

  {file:/project/prompts/overseer_prompt.md}
tools:
  read: true
  write: true
  edit: true
  bash: true
---
