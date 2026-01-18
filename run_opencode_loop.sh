#!/bin/bash

PROMPT="${1:-prompt here}"

for i in {1..20}; do
    echo "=== Run $i/20 ==="
    opencode run "$PROMPT"
    echo ""
done
