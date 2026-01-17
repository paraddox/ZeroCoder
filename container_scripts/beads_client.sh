#!/bin/bash
# =============================================================================
# Beads API Client
# =============================================================================
# Wrapper script that calls host API instead of bd directly.
# Agents use this to perform beads operations.
#
# Usage:
#   ./beads_client.sh list [--status=open|in_progress|closed]
#   ./beads_client.sh ready
#   ./beads_client.sh show <issue_id>
#   ./beads_client.sh stats
#   ./beads_client.sh create --title "..." [--type task] [--priority 2] [--description "..."]
#   ./beads_client.sh update <issue_id> [--status in_progress] [--title "..."] [--priority 1]
#   ./beads_client.sh close <issue_id> [--reason "..."]
#   ./beads_client.sh reopen <issue_id>
#   ./beads_client.sh sync
#   ./beads_client.sh comments <issue_id> --add "comment text"
#   ./beads_client.sh dep add <issue_id> <depends_on>
#
# Environment:
#   HOST_API_URL - Base URL of host API (default: http://host.docker.internal:8000)
#   PROJECT_NAME - Project name (required)

set -e

HOST_API="${HOST_API_URL:-http://host.docker.internal:8000}"
PROJECT="${PROJECT_NAME:-}"

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

    show)
        ISSUE_ID="${1:-}"
        if [ -z "$ISSUE_ID" ]; then
            echo "Error: issue_id required" >&2
            exit 1
        fi
        # Skip --json flag if present
        curl -s "$BASE_URL/show/$ISSUE_ID"
        ;;

    stats)
        curl -s "$BASE_URL/stats"
        ;;

    create)
        # Parse create options
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
                    # Convert P0-P4 to 0-4
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
                    # Ignored, always returns JSON
                    ;;
            esac
            shift
        done

        if [ -z "$TITLE" ]; then
            echo "Error: --title required" >&2
            exit 1
        fi

        # Build JSON body
        LABELS_JSON="[]"
        if [ -n "$LABELS" ]; then
            # Convert comma-separated labels to JSON array
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

        # Parse update options
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

        # Build JSON body with only provided fields
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

        # Parse optional --reason
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
                -d "$(jq -n --arg reason "$REASON" '{reason: $reason}')"
        else
            curl -s -X POST "$BASE_URL/close/$ISSUE_ID"
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

        # Parse --add flag
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
Beads API Client - Wrapper for host beads API

Usage:
  beads_client.sh list [--status=open|in_progress|closed]
  beads_client.sh ready
  beads_client.sh show <issue_id>
  beads_client.sh stats
  beads_client.sh create --title "..." [--type task] [--priority 2] [--description "..."]
  beads_client.sh update <issue_id> [--status in_progress] [--title "..."]
  beads_client.sh close <issue_id> [--reason "..."]
  beads_client.sh reopen <issue_id>
  beads_client.sh sync
  beads_client.sh comments <issue_id> --add "comment text"
  beads_client.sh dep add <issue_id> <depends_on>

Environment:
  HOST_API_URL  - Host API base URL (default: http://host.docker.internal:8000)
  PROJECT_NAME  - Project name (required)
EOF
        ;;

    *)
        echo "Error: Unknown command: $CMD" >&2
        echo "Run 'beads_client.sh help' for usage" >&2
        exit 1
        ;;
esac
