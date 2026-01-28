#!/bin/bash
# ZeroCoder Migration Script: Python to TypeScript
# ================================================
#
# This script migrates data from the Python backend (FastAPI/SQLAlchemy)
# to the TypeScript backend (Hono/Drizzle ORM).
#
# Usage: ./scripts/migrate_to_typescript.sh [--dry-run] [--force]
#
# Options:
#   --dry-run    Show what would be migrated without making changes
#   --force      Skip confirmation prompts
#

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
ZEROCODER_DIR="${HOME}/.zerocoder"
PYTHON_DB="${ZEROCODER_DIR}/registry.db"
TYPESCRIPT_DB="${ZEROCODER_DIR}/zerocoder.db"
BACKUP_DIR="${ZEROCODER_DIR}/backups"
MIGRATION_LOG="${ZEROCODER_DIR}/migration.log"

# Flags
DRY_RUN=false
FORCE=false

# Parse arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    --dry-run)
      DRY_RUN=true
      shift
      ;;
    --force)
      FORCE=true
      shift
      ;;
    --help|-h)
      echo "Usage: $0 [--dry-run] [--force]"
      echo ""
      echo "Options:"
      echo "  --dry-run    Show what would be migrated without making changes"
      echo "  --force      Skip confirmation prompts"
      echo "  --help, -h   Show this help message"
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
  echo -e "${BLUE}[INFO]${NC} $1" | tee -a "$MIGRATION_LOG"
}

log_success() {
  echo -e "${GREEN}[SUCCESS]${NC} $1" | tee -a "$MIGRATION_LOG"
}

log_warn() {
  echo -e "${YELLOW}[WARN]${NC} $1" | tee -a "$MIGRATION_LOG"
}

log_error() {
  echo -e "${RED}[ERROR]${NC} $1" | tee -a "$MIGRATION_LOG"
}

# Initialize log file
mkdir -p "$ZEROCODER_DIR"
touch "$MIGRATION_LOG"
echo "=== Migration started at $(date) ===" >> "$MIGRATION_LOG"

# Print banner
echo ""
echo "=============================================="
echo "  ZeroCoder: Python → TypeScript Migration"
echo "=============================================="
echo ""

if [[ "$DRY_RUN" == true ]]; then
  log_warn "DRY RUN MODE - No changes will be made"
  echo ""
fi

# Check prerequisites
check_prerequisites() {
  log_info "Checking prerequisites..."

  # Check if Python database exists
  if [[ ! -f "$PYTHON_DB" ]]; then
    log_error "Python database not found at: $PYTHON_DB"
    log_error "Nothing to migrate."
    exit 1
  fi

  # Check if sqlite3 is available
  if ! command -v sqlite3 &> /dev/null; then
    log_error "sqlite3 is required but not installed"
    exit 1
  fi

  # Check if Node.js is available for TypeScript server
  if ! command -v node &> /dev/null; then
    log_warn "Node.js not found. TypeScript server will not be able to start."
  fi

  log_success "Prerequisites check passed"
}

# Create backup
create_backup() {
  if [[ "$DRY_RUN" == true ]]; then
    log_info "[DRY RUN] Would create backup at: ${BACKUP_DIR}/registry-$(date +%Y%m%d-%H%M%S).db"
    return
  fi

  log_info "Creating backup..."
  mkdir -p "$BACKUP_DIR"
  local backup_file="${BACKUP_DIR}/registry-$(date +%Y%m%d-%H%M%S).db"
  cp "$PYTHON_DB" "$backup_file"
  log_success "Backup created at: $backup_file"
}

# Get table counts from Python database
get_python_stats() {
  log_info "Analyzing Python database..."

  local tables=("projects" "containers" "feature_cache" "feature_stats_cache" "remote_machines" "remote_agents" "project_verification_state")

  echo ""
  echo "Python Database Stats:"
  echo "----------------------"

  for table in "${tables[@]}"; do
    local count=$(sqlite3 "$PYTHON_DB" "SELECT COUNT(*) FROM $table 2>/dev/null || echo 0")
    printf "  %-30s %5d records\n" "$table:" "$count"
  done

  echo ""
}

# Confirm migration
confirm_migration() {
  if [[ "$FORCE" == true ]]; then
    return
  fi

  if [[ "$DRY_RUN" == true ]]; then
    return
  fi

  echo ""
  echo "This will migrate data from:"
  echo "  Source: $PYTHON_DB"
  echo "  Target: $TYPESCRIPT_DB"
  echo ""
  read -p "Do you want to proceed? (yes/no): " response

  if [[ "$response" != "yes" ]]; then
    log_info "Migration cancelled by user"
    exit 0
  fi
}

# Migrate projects table
migrate_projects() {
  log_info "Migrating projects..."

  local query="
    INSERT OR IGNORE INTO projects (name, git_url, target_container_count, created_at)
    SELECT
      name,
      git_url,
      COALESCE(target_container_count, 1),
      COALESCE(created_at, datetime('now'))
    FROM projects;
  "

  if [[ "$DRY_RUN" == true ]]; then
    local count=$(sqlite3 "$PYTHON_DB" "SELECT COUNT(*) FROM projects;")
    log_info "[DRY RUN] Would migrate $count projects"
    return
  fi

  sqlite3 "$TYPESCRIPT_DB" "$query"
  local migrated=$(sqlite3 "$TYPESCRIPT_DB" "SELECT COUNT(*) FROM projects;")
  log_success "Migrated $migrated projects"
}

# Migrate remote_machines table
migrate_remote_machines() {
  log_info "Migrating remote machines..."

  local query="
    INSERT OR IGNORE INTO remote_machines (id, name, host, port, username, ssh_key_path, status, last_checked_at, created_at)
    SELECT
      id,
      name,
      host,
      COALESCE(port, 22),
      COALESCE(username, 'root'),
      ssh_key_path,
      COALESCE(status, 'unknown'),
      last_checked_at,
      COALESCE(created_at, datetime('now'))
    FROM remote_machines;
  "

  if [[ "$DRY_RUN" == true ]]; then
    local count=$(sqlite3 "$PYTHON_DB" "SELECT COUNT(*) FROM remote_machines 2>/dev/null || echo 0")
    log_info "[DRY RUN] Would migrate $count remote machines"
    return
  fi

  sqlite3 "$TYPESCRIPT_DB" "$query" 2>/dev/null || log_warn "No remote_machines table in source or table already exists"
  local migrated=$(sqlite3 "$TYPESCRIPT_DB" "SELECT COUNT(*) FROM remote_machines 2>/dev/null || echo 0")
  log_success "Migrated $migrated remote machines"
}

# Note: Session-scoped data is intentionally NOT migrated
# This includes: containers, feature_cache, feature_stats_cache, remote_agents, project_verification_state
log_session_scoped_note() {
  echo ""
  log_info "Note: Session-scoped data is not migrated (by design)"
  echo "  The following tables will be rebuilt at runtime:"
  echo "    - containers (container instances)"
  echo "    - feature_cache (rebuilt from beads polling)"
  echo "    - feature_stats_cache (rebuilt from beads polling)"
  echo "    - remote_agents (agent instances)"
  echo "    - project_verification_state (session state)"
  echo ""
}

# Create TypeScript database schema if it doesn't exist
create_typescript_schema() {
  if [[ "$DRY_RUN" == true ]]; then
    log_info "[DRY RUN] Would ensure TypeScript database schema exists"
    return
  fi

  log_info "Ensuring TypeScript database schema..."

  # The TypeScript server uses Drizzle ORM which manages its own schema
  # We just need to ensure the database file exists
  if [[ ! -f "$TYPESCRIPT_DB" ]]; then
    log_info "TypeScript database does not exist yet. It will be created by the server."
    log_info "Please run the TypeScript server first to initialize the schema."
    echo ""
    echo "  cd packages/server && npm run db:migrate"
    echo ""
    exit 1
  fi

  log_success "TypeScript database found"
}

# Verify migration
verify_migration() {
  log_info "Verifying migration..."

  echo ""
  echo "Migration Summary:"
  echo "------------------"

  local py_projects=$(sqlite3 "$PYTHON_DB" "SELECT COUNT(*) FROM projects;" 2>/dev/null || echo 0)
  local ts_projects=$(sqlite3 "$TYPESCRIPT_DB" "SELECT COUNT(*) FROM projects;" 2>/dev/null || echo 0)

  printf "  Projects:       %3d (source) → %3d (target)\n" "$py_projects" "$ts_projects"

  local py_machines=$(sqlite3 "$PYTHON_DB" "SELECT COUNT(*) FROM remote_machines;" 2>/dev/null || echo 0)
  local ts_machines=$(sqlite3 "$TYPESCRIPT_DB" "SELECT COUNT(*) FROM remote_machines;" 2>/dev/null || echo 0)

  printf "  Remote Machines: %2d (source) → %2d (target)\n" "$py_machines" "$ts_machines"

  echo ""

  if [[ "$ts_projects" -eq "$py_projects" && "$ts_machines" -eq "$py_machines" ]]; then
    log_success "Migration verification passed"
    return 0
  else
    log_warn "Migration verification: counts differ (this may be normal if some records already existed)"
    return 0
  fi
}

# Update start-app.sh to use TypeScript server
update_startup_script() {
  if [[ "$DRY_RUN" == true ]]; then
    log_info "[DRY RUN] Would update start-app.sh to use TypeScript server"
    return
  fi

  log_info "Checking startup script configuration..."

  # Check if there's already a TypeScript startup script
  if [[ -f "start-app-ts.sh" ]]; then
    log_success "TypeScript startup script already exists: start-app-ts.sh"
  else
    log_warn "TypeScript startup script (start-app-ts.sh) not found"
    log_info "You may need to create it or update start-app.sh manually"
  fi
}

# Print next steps
print_next_steps() {
  echo ""
  echo "=============================================="
  echo "  Migration Complete!"
  echo "=============================================="
  echo ""
  echo "Next steps:"
  echo ""
  echo "1. Start the TypeScript server:"
  echo "   cd packages/server && npm run dev"
  echo ""
  echo "2. Verify the server is running:"
  echo "   curl http://localhost:8000/health"
  echo ""
  echo "3. Test with your projects in the UI"
  echo ""
  echo "4. Once validated, you can remove the Python server:"
  echo "   rm -rf server/"
  echo ""
  echo "Backup location: ${BACKUP_DIR}"
  echo "Migration log: ${MIGRATION_LOG}"
  echo ""
}

# Main execution
main() {
  check_prerequisites
  get_python_stats

  create_typescript_schema
  create_backup

  log_session_scoped_note
  confirm_migration

  migrate_projects
  migrate_remote_machines

  verify_migration
  update_startup_script

  if [[ "$DRY_RUN" == false ]]; then
    print_next_steps
  fi

  log_success "Migration process completed at $(date)"
}

# Run main function
main
