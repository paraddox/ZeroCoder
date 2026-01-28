#!/bin/bash
# ZeroCoder Cutover Script: Switch from Python to TypeScript Server
# ================================================================
#
# This script performs the cutover from the Python backend to the TypeScript backend.
# It handles:
# - Stopping the Python server
# - Running database migration
# - Starting the TypeScript server
# - Health check validation
# - Rollback capability
#
# Usage: ./scripts/cutover_to_typescript.sh [--skip-migration] [--port PORT] [--dry-run]
#
# Options:
#   --skip-migration    Skip database migration (assume already migrated)
#   --port PORT         Use specific port for TypeScript server (default: 8000)
#   --dry-run           Show what would be done without making changes
#   --rollback          Rollback to Python server
#

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
ZEROCODER_DIR="${HOME}/.zerocoder"
PID_FILE="/tmp/zerocoder-cutover.pid"
CUTOVER_LOG="${ZEROCODER_DIR}/cutover.log"

# Default settings
SKIP_MIGRATION=false
DRY_RUN=false
ROLLBACK=false
TS_PORT="${PORT:-8000}"
PYTHON_PORT="${PYTHON_PORT:-8888}"

# Parse arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    --skip-migration)
      SKIP_MIGRATION=true
      shift
      ;;
    --port)
      TS_PORT="$2"
      shift 2
      ;;
    --dry-run)
      DRY_RUN=true
      shift
      ;;
    --rollback)
      ROLLBACK=true
      shift
      ;;
    --help|-h)
      echo "Usage: $0 [OPTIONS]"
      echo ""
      echo "Options:"
      echo "  --skip-migration    Skip database migration"
      echo "  --port PORT         TypeScript server port (default: 8000)"
      echo "  --dry-run           Show what would be done"
      echo "  --rollback          Rollback to Python server"
      echo "  --help, -h          Show this help message"
      echo ""
      echo "Environment Variables:"
      echo "  PORT                TypeScript server port"
      echo "  PYTHON_PORT         Python server port"
      exit 0
      ;;
    *)
      echo "Unknown option: $1"
      echo "Use --help for usage information"
      exit 1
      ;;
  esac
done

# Logging functions
log_info() {
  echo -e "${BLUE}[INFO]${NC} $1" | tee -a "$CUTOVER_LOG"
}

log_success() {
  echo -e "${GREEN}[SUCCESS]${NC} $1" | tee -a "$CUTOVER_LOG"
}

log_warn() {
  echo -e "${YELLOW}[WARN]${NC} $1" | tee -a "$CUTOVER_LOG"
}

log_error() {
  echo -e "${RED}[ERROR]${NC} $1" | tee -a "$CUTOVER_LOG"
}

log_step() {
  echo ""
  echo -e "${BLUE}▶ $1${NC}" | tee -a "$CUTOVER_LOG"
}

# Initialize logging
mkdir -p "$ZEROCODER_DIR"
touch "$CUTOVER_LOG"
echo "=== Cutover started at $(date) ===" >> "$CUTOVER_LOG"

# Print banner
echo ""
echo "=============================================="
echo "  ZeroCoder: Python → TypeScript Cutover"
echo "=============================================="
echo ""

if [[ "$DRY_RUN" == true ]]; then
  log_warn "DRY RUN MODE - No changes will be made"
  echo ""
fi

if [[ "$ROLLBACK" == true ]]; then
  log_warn "ROLLBACK MODE - Reverting to Python server"
  echo ""
fi

# Check if server is running on a port
check_server() {
  local port=$1
  local timeout=${2:-2}

  if curl -s -o /dev/null -w "%{http_code}" --max-time "$timeout" "http://localhost:$port/health" 2>/dev/null | grep -q "200"; then
    return 0
  else
    return 1
  fi
}

# Get PID of process using a port
get_pid_on_port() {
  local port=$1
  lsof -ti :"$port" 2>/dev/null || echo ""
}

# Stop Python server
stop_python_server() {
  log_step "Step 1: Stopping Python server..."

  if [[ "$DRY_RUN" == true ]]; then
    log_info "[DRY RUN] Would stop Python server on port $PYTHON_PORT"
    return
  fi

  local python_pid=$(get_pid_on_port "$PYTHON_PORT")

  if [[ -n "$python_pid" ]]; then
    log_info "Found Python server (PID: $python_pid) on port $PYTHON_PORT"
    log_info "Sending graceful shutdown signal..."

    kill -TERM "$python_pid" 2>/dev/null || true

    # Wait for graceful shutdown
    local count=0
    while [[ $count -lt 10 ]]; do
      if ! kill -0 "$python_pid" 2>/dev/null; then
        log_success "Python server stopped gracefully"
        return
      fi
      sleep 1
      ((count++))
    done

    # Force kill if still running
    log_warn "Python server didn't stop gracefully, force killing..."
    kill -9 "$python_pid" 2>/dev/null || true
    sleep 1

    if ! kill -0 "$python_pid" 2>/dev/null; then
      log_success "Python server stopped"
    else
      log_error "Failed to stop Python server"
      return 1
    fi
  else
    log_info "No Python server found on port $PYTHON_PORT"
  fi
}

# Stop TypeScript server
stop_typescript_server() {
  log_step "Step 1: Stopping TypeScript server..."

  if [[ "$DRY_RUN" == true ]]; then
    log_info "[DRY RUN] Would stop TypeScript server on port $TS_PORT"
    return
  fi

  local ts_pid=$(get_pid_on_port "$TS_PORT")

  if [[ -n "$ts_pid" ]]; then
    log_info "Found TypeScript server (PID: $ts_pid) on port $TS_PORT"
    kill -TERM "$ts_pid" 2>/dev/null || true
    sleep 2

    if kill -0 "$ts_pid" 2>/dev/null; then
      kill -9 "$ts_pid" 2>/dev/null || true
    fi

    log_success "TypeScript server stopped"
  else
    log_info "No TypeScript server found on port $TS_PORT"
  fi
}

# Run database migration
run_migration() {
  if [[ "$SKIP_MIGRATION" == true ]]; then
    log_info "Skipping database migration (--skip-migration)"
    return
  fi

  log_step "Step 2: Running database migration..."

  if [[ "$DRY_RUN" == true ]]; then
    log_info "[DRY RUN] Would run: ${SCRIPT_DIR}/migrate_to_typescript.sh --force"
    return
  fi

  if [[ -f "${SCRIPT_DIR}/migrate_to_typescript.sh" ]]; then
    "${SCRIPT_DIR}/migrate_to_typescript.sh" --force
    if [[ $? -eq 0 ]]; then
      log_success "Database migration completed"
    else
      log_error "Database migration failed"
      return 1
    fi
  else
    log_error "Migration script not found: ${SCRIPT_DIR}/migrate_to_typescript.sh"
    return 1
  fi
}

# Build TypeScript server
build_typescript_server() {
  log_step "Step 3: Building TypeScript server..."

  if [[ "$DRY_RUN" == true ]]; then
    log_info "[DRY RUN] Would build TypeScript server"
    return
  fi

  cd "$PROJECT_ROOT/packages/server"

  # Check if node_modules exists
  if [[ ! -d "node_modules" ]]; then
    log_info "Installing dependencies..."
    npm install
  fi

  # Build the server
  log_info "Compiling TypeScript..."
  if npm run build; then
    log_success "TypeScript server built successfully"
  else
    log_error "Failed to build TypeScript server"
    return 1
  fi

  cd "$PROJECT_ROOT"
}

# Start TypeScript server
start_typescript_server() {
  log_step "Step 4: Starting TypeScript server..."

  if [[ "$DRY_RUN" == true ]]; then
    log_info "[DRY RUN] Would start TypeScript server on port $TS_PORT"
    return
  fi

  cd "$PROJECT_ROOT/packages/server"

  # Set environment variables
  export PORT="$TS_PORT"
  export HOST="${HOST:-127.0.0.1}"

  # Start server in background
  log_info "Starting server on http://$HOST:$PORT..."
  nohup npm run start > "${ZEROCODER_DIR}/typescript-server.log" 2>&1 &
  local server_pid=$!

  # Save PID
  echo "$server_pid" > "$PID_FILE"

  # Wait for server to be ready
  log_info "Waiting for server to be ready..."
  local count=0
  while [[ $count -lt 30 ]]; do
    if check_server "$TS_PORT" 1; then
      log_success "TypeScript server is running (PID: $server_pid)"
      return 0
    fi
    sleep 1
    ((count++))
    echo -n "."
  done
  echo ""

  log_error "Server failed to start within 30 seconds"
  log_error "Check logs: ${ZEROCODER_DIR}/typescript-server.log"
  return 1
}

# Start Python server (for rollback)
start_python_server() {
  log_step "Step 3: Starting Python server (rollback)..."

  if [[ "$DRY_RUN" == true ]]; then
    log_info "[DRY RUN] Would start Python server on port $PYTHON_PORT"
    return
  fi

  cd "$PROJECT_ROOT"

  # Check if venv exists
  if [[ ! -d "venv" ]]; then
    log_error "Python virtual environment not found"
    return 1
  fi

  source venv/bin/activate

  export PORT="$PYTHON_PORT"
  export HOST="${HOST:-127.0.0.1}"

  log_info "Starting Python server on http://$HOST:$PORT..."
  nohup python -m uvicorn server.main:app --host "$HOST" --port "$PORT" > "${ZEROCODER_DIR}/python-server.log" 2>&1 &
  local server_pid=$!

  echo "$server_pid" > "$PID_FILE"

  # Wait for server to be ready
  log_info "Waiting for server to be ready..."
  local count=0
  while [[ $count -lt 30 ]]; do
    if check_server "$PYTHON_PORT" 1; then
      log_success "Python server is running (PID: $server_pid)"
      return 0
    fi
    sleep 1
    ((count++))
    echo -n "."
  done
  echo ""

  log_error "Server failed to start within 30 seconds"
  return 1
}

# Validate cutover
validate_cutover() {
  log_step "Step 5: Validating cutover..."

  if [[ "$DRY_RUN" == true ]]; then
    log_info "[DRY RUN] Would validate server health"
    return
  fi

  local port=$1

  # Health check
  log_info "Performing health check..."

  local retries=5
  local count=0

  while [[ $count -lt $retries ]]; do
    if check_server "$port" 2; then
      log_success "Health check passed"

      # Get server info
      local health_response=$(curl -s --max-time 2 "http://localhost:$port/health" 2>/dev/null || echo "{}")
      log_info "Server response: $health_response"

      return 0
    fi

    ((count++))
    log_warn "Health check failed, retrying... ($count/$retries)"
    sleep 2
  done

  log_error "Health check failed after $retries attempts"
  return 1
}

# Create cutover marker
create_cutover_marker() {
  if [[ "$DRY_RUN" == true ]]; then
    return
  fi

  local marker_file="${ZEROCODER_DIR}/.typescript-active"

  if [[ "$ROLLBACK" == true ]]; then
    rm -f "$marker_file"
    log_info "Removed TypeScript active marker"
  else
    echo "$(date)" > "$marker_file"
    log_info "Created TypeScript active marker"
  fi
}

# Print status
print_status() {
  echo ""
  echo "=============================================="
  if [[ "$ROLLBACK" == true ]]; then
    echo "  Rollback Complete!"
  else
    echo "  Cutover Complete!"
  fi
  echo "=============================================="
  echo ""

  if [[ "$DRY_RUN" == true ]]; then
    log_warn "This was a dry run. No actual changes were made."
    echo ""
    return
  fi

  if [[ "$ROLLBACK" == true ]]; then
    echo "Python server is now running on port $PYTHON_PORT"
    echo ""
    echo "To switch back to TypeScript:"
    echo "  $0"
    echo ""
  else
    echo "TypeScript server is now running on port $TS_PORT"
    echo ""
    echo "Server URL: http://localhost:$TS_PORT"
    echo "Health check: http://localhost:$TS_PORT/health"
    echo ""
    echo "To rollback to Python server:"
    echo "  $0 --rollback"
    echo ""
  fi

  echo "Logs:"
  if [[ "$ROLLBACK" == true ]]; then
    echo "  Python server: ${ZEROCODER_DIR}/python-server.log"
  else
    echo "  TypeScript server: ${ZEROCODER_DIR}/typescript-server.log"
  fi
  echo "  Cutover log: ${CUTOVER_LOG}"
  echo ""
}

# Main cutover process
main_cutover() {
  log_info "Starting cutover to TypeScript server..."

  # Pre-checks
  if ! check_server "$PYTHON_PORT" 2; then
    log_warn "Python server is not currently running on port $PYTHON_PORT"
  fi

  # Step 1: Stop Python server
  stop_python_server

  # Step 2: Run migration
  run_migration

  # Step 3: Build TypeScript server
  build_typescript_server

  # Step 4: Start TypeScript server
  start_typescript_server

  # Step 5: Validate
  if validate_cutover "$TS_PORT"; then
    create_cutover_marker
    log_success "Cutover completed successfully!"
  else
    log_error "Cutover validation failed!"
    log_warn "Consider rolling back: $0 --rollback"
    return 1
  fi

  print_status
}

# Rollback process
main_rollback() {
  log_info "Starting rollback to Python server..."

  # Step 1: Stop TypeScript server
  stop_typescript_server

  # Step 2: Start Python server
  start_python_server

  # Step 3: Validate
  if validate_cutover "$PYTHON_PORT"; then
    create_cutover_marker
    log_success "Rollback completed successfully!"
  else
    log_error "Rollback validation failed!"
    return 1
  fi

  print_status
}

# Main execution
main() {
  if [[ "$ROLLBACK" == true ]]; then
    main_rollback
  else
    main_cutover
  fi
}

# Handle errors
trap 'log_error "Cutover interrupted"; exit 1' INT TERM

# Run main
main
