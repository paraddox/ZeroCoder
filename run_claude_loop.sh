#!/bin/bash

PROMPT="${1:-prompt here}"

for i in {1..20}; do
    echo "=== Run $i/10 ==="
    claude --dangerously-skip-permissions -p "$PROMPT"
    echo ""
done
