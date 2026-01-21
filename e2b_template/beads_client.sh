#!/bin/bash
# =============================================================================
# Beads API Client (E2B Sandbox Version)
# =============================================================================
# Wrapper script that calls host API for beads operations.
# Agents use this to interact with the beads issue tracker.
#
# Key difference from Docker version:
# - Uses HOST_API_URL directly (no host.docker.internal)
# - HOST_API_URL must be a publicly accessible URL or tunnel
#
# Usage:
#   beads_client claim                 # Get next available issue (RECOMMENDED)
#   beads_client close <issue_id>      # Mark issue complete
#   beads_client list [--status=open|in_progress|closed]
#   beads_client show <issue_id>
#   beads_client stats
#   beads_client create --title "..." [--type task] [--priority 2]
#   beads_client update <issue_id> [--status in_progress]
#   beads_client reopen <issue_id>
#   beads_client sync
#
# Environment:
#   HOST_API_URL - Host API URL (REQUIRED - must be publicly accessible)
#   PROJECT_NAME - Project name (REQUIRED)
#   CONTAINER_NUMBER - Sandbox/container number (default: 1)

set -e

HOST_API="${HOST_API_URL:-}"
PROJECT="${PROJECT_NAME:-}"
CONTAINER_NUM="${CONTAINER_NUMBER:-1}"

if [ -z "$HOST_API" ]; then
    echo "Error: HOST_API_URL environment variable not set" >&2
    exit 1
fi

if [ -z "$PROJECT" ]; then
    echo "Error: PROJECT_NAME environment variable not set" >&2
    exit 1
fi

BASE_URL="$HOST_API/api/projects/$PROJECT/beads"

# Parse command
CMD="${1:-}"
shift 2>/dev/null || true

case "$CMD" in
    list)
        # Parse optional --status flag
        STATUS=""
        while [[ $# -gt 0 ]]; do
            case "$1" in
                --status=*)
                    STATUS="${1#*=}"
                    ;;
                --status)
                    STATUS="$2"
                    shift
                    ;;
                --json)
                    # Ignored, always returns JSON
                    ;;
            esac
            shift
        done

        if [ -n "$STATUS" ]; then
            curl -s "$BASE_URL/list?status=$STATUS"
        else
            curl -s "$BASE_URL/list"
        fi
        ;;

    ready)
        curl -s "$BASE_URL/ready"
        ;;

    claim)
        # Atomically claim the next available issue
        RESPONSE=$(curl -s -X POST "$BASE_URL/claim" \
            -H "X-Container-Number: $CONTAINER_NUM")

        SUCCESS=$(echo "$RESPONSE" | jq -r '.success // false')
        if [ "$SUCCESS" = "true" ]; then
            echo "$RESPONSE" | jq '.issue'
        else
            MESSAGE=$(echo "$RESPONSE" | jq -r '.message // "No issues available"')
            echo "Error: $MESSAGE" >&2
            exit 1
        fi
        ;;

    show)
        ISSUE_ID="${1:-}"
        if [ -z "$ISSUE_ID" ]; then
            echo "Error: issue_id required" >&2
            exit 1
        fi
        curl -s "$BASE_URL/show/$ISSUE_ID"
        ;;

    stats)
        curl -s "$BASE_URL/stats"
        ;;

    create)
        TITLE=""
        TYPE="task"
        PRIORITY="2"
        DESCRIPTION=""
        LABELS=""

        while [[ $# -gt 0 ]]; do
            case "$1" in
                --title=*)
                    TITLE="${1#*=}"
                    ;;
                --title)
                    TITLE="$2"
                    shift
                    ;;
                --type=*)
                    TYPE="${1#*=}"
                    ;;
                --type)
                    TYPE="$2"
                    shift
                    ;;
                --priority=*)
                    PRIORITY="${1#*=}"
                    PRIORITY="${PRIORITY#P}"
                    ;;
                --priority)
                    PRIORITY="$2"
                    PRIORITY="${PRIORITY#P}"
                    shift
                    ;;
                --description=*)
                    DESCRIPTION="${1#*=}"
                    ;;
                --description)
                    DESCRIPTION="$2"
                    shift
                    ;;
                --labels=*)
                    LABELS="${1#*=}"
                    ;;
                --labels)
                    LABELS="$2"
                    shift
                    ;;
                --json)
                    ;;
            esac
            shift
        done

        if [ -z "$TITLE" ]; then
            echo "Error: --title required" >&2
            exit 1
        fi

        LABELS_JSON="[]"
        if [ -n "$LABELS" ]; then
            LABELS_JSON=$(echo "$LABELS" | jq -R 'split(",")')
        fi

        curl -s -X POST "$BASE_URL/create" \
            -H "Content-Type: application/json" \
            -d "$(jq -n \
                --arg title "$TITLE" \
                --arg type "$TYPE" \
                --argjson priority "$PRIORITY" \
                --arg description "$DESCRIPTION" \
                --argjson labels "$LABELS_JSON" \
                '{title: $title, type: $type, priority: $priority, description: $description, labels: $labels}')"
        ;;

    update)
        ISSUE_ID="${1:-}"
        if [ -z "$ISSUE_ID" ]; then
            echo "Error: issue_id required" >&2
            exit 1
        fi
        shift

        TITLE=""
        STATUS=""
        PRIORITY=""
        DESCRIPTION=""
        ASSIGNEE=""

        while [[ $# -gt 0 ]]; do
            case "$1" in
                --title=*)
                    TITLE="${1#*=}"
                    ;;
                --title)
                    TITLE="$2"
                    shift
                    ;;
                --status=*)
                    STATUS="${1#*=}"
                    ;;
                --status)
                    STATUS="$2"
                    shift
                    ;;
                --priority=*)
                    PRIORITY="${1#*=}"
                    PRIORITY="${PRIORITY#P}"
                    ;;
                --priority)
                    PRIORITY="$2"
                    PRIORITY="${PRIORITY#P}"
                    shift
                    ;;
                --description=*)
                    DESCRIPTION="${1#*=}"
                    ;;
                --description)
                    DESCRIPTION="$2"
                    shift
                    ;;
                --assignee=*)
                    ASSIGNEE="${1#*=}"
                    ;;
                --assignee)
                    ASSIGNEE="$2"
                    shift
                    ;;
            esac
            shift
        done

        JSON_BODY="{}"
        [ -n "$TITLE" ] && JSON_BODY=$(echo "$JSON_BODY" | jq --arg v "$TITLE" '. + {title: $v}')
        [ -n "$STATUS" ] && JSON_BODY=$(echo "$JSON_BODY" | jq --arg v "$STATUS" '. + {status: $v}')
        [ -n "$PRIORITY" ] && JSON_BODY=$(echo "$JSON_BODY" | jq --argjson v "$PRIORITY" '. + {priority: $v}')
        [ -n "$DESCRIPTION" ] && JSON_BODY=$(echo "$JSON_BODY" | jq --arg v "$DESCRIPTION" '. + {description: $v}')
        [ -n "$ASSIGNEE" ] && JSON_BODY=$(echo "$JSON_BODY" | jq --arg v "$ASSIGNEE" '. + {assignee: $v}')

        curl -s -X PATCH "$BASE_URL/update/$ISSUE_ID" \
            -H "Content-Type: application/json" \
            -d "$JSON_BODY"
        ;;

    close)
        ISSUE_ID="${1:-}"
        if [ -z "$ISSUE_ID" ]; then
            echo "Error: issue_id required" >&2
            exit 1
        fi
        shift 2>/dev/null || true

        REASON=""
        while [[ $# -gt 0 ]]; do
            case "$1" in
                --reason=*)
                    REASON="${1#*=}"
                    ;;
                --reason)
                    REASON="$2"
                    shift
                    ;;
            esac
            shift
        done

        if [ -n "$REASON" ]; then
            curl -s -X POST "$BASE_URL/close/$ISSUE_ID" \
                -H "Content-Type: application/json" \
                -H "X-Container-Number: $CONTAINER_NUM" \
                -d "$(jq -n --arg reason "$REASON" '{reason: $reason}')"
        else
            curl -s -X POST "$BASE_URL/close/$ISSUE_ID" \
                -H "X-Container-Number: $CONTAINER_NUM"
        fi
        ;;

    reopen)
        ISSUE_ID="${1:-}"
        if [ -z "$ISSUE_ID" ]; then
            echo "Error: issue_id required" >&2
            exit 1
        fi
        curl -s -X POST "$BASE_URL/reopen/$ISSUE_ID"
        ;;

    sync)
        curl -s -X POST "$BASE_URL/sync"
        ;;

    comments)
        ISSUE_ID="${1:-}"
        if [ -z "$ISSUE_ID" ]; then
            echo "Error: issue_id required" >&2
            exit 1
        fi
        shift

        COMMENT=""
        while [[ $# -gt 0 ]]; do
            case "$1" in
                --add=*)
                    COMMENT="${1#*=}"
                    ;;
                --add)
                    COMMENT="$2"
                    shift
                    ;;
            esac
            shift
        done

        if [ -z "$COMMENT" ]; then
            echo "Error: --add \"comment text\" required" >&2
            exit 1
        fi

        curl -s -X POST "$BASE_URL/comments/$ISSUE_ID" \
            -H "Content-Type: application/json" \
            -d "$(jq -n --arg comment "$COMMENT" '{comment: $comment}')"
        ;;

    dep)
        SUBCMD="${1:-}"
        case "$SUBCMD" in
            add)
                ISSUE_ID="${2:-}"
                DEPENDS_ON="${3:-}"
                if [ -z "$ISSUE_ID" ] || [ -z "$DEPENDS_ON" ]; then
                    echo "Error: dep add requires issue_id and depends_on" >&2
                    exit 1
                fi
                curl -s -X POST "$BASE_URL/dep/add?issue_id=$ISSUE_ID&depends_on=$DEPENDS_ON"
                ;;
            *)
                echo "Error: Unknown dep subcommand: $SUBCMD" >&2
                exit 1
                ;;
        esac
        ;;

    ""|help|-h|--help)
        cat << 'EOF'
Beads API Client (E2B Sandbox Version)

=== CODER AGENT: You only need these 2 commands ===

  beads_client claim                 # Get next available issue (returns JSON)
  beads_client close <issue_id>      # Mark issue complete when done

The claim command is ATOMIC - the server locks and assigns different
issues to different agents. No need for ready/update/sync.

=== OVERSEER/ADVANCED USAGE ===

  beads_client list [--status=open|in_progress|closed]
  beads_client ready
  beads_client show <issue_id>
  beads_client stats
  beads_client create --title "..." [--type task] [--priority 2]
  beads_client update <issue_id> [--status in_progress]
  beads_client reopen <issue_id>
  beads_client sync
  beads_client comments <issue_id> --add "comment text"
  beads_client dep add <issue_id> <depends_on>

Environment:
  HOST_API_URL     - Host API URL (REQUIRED - must be publicly accessible)
  PROJECT_NAME     - Project name (REQUIRED)
  CONTAINER_NUMBER - Sandbox number (default: 1)
EOF
        ;;

    *)
        echo "Error: Unknown command: $CMD" >&2
        echo "Run 'beads_client help' for usage" >&2
        exit 1
        ;;
esac
