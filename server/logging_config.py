"""
Centralized Logging Configuration
=================================

Provides centralized logging with 24-hour retention for all server subsystems.
Log files are stored at ~/.zerocoder/logs/
"""

import logging
import time
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

LOGS_DIR = Path.home() / ".zerocoder" / "logs"
LOG_RETENTION_HOURS = 24


def cleanup_old_logs():
    """Remove log files older than 24 hours."""
    if not LOGS_DIR.exists():
        return

    cutoff = time.time() - (LOG_RETENTION_HOURS * 3600)
    for log_file in LOGS_DIR.glob("*.log*"):
        try:
            if log_file.stat().st_mtime < cutoff:
                log_file.unlink()
        except OSError:
            pass  # File may have been deleted by another process


def setup_logging():
    """Initialize centralized logging with 24h retention."""
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    # Clean up old logs on startup
    cleanup_old_logs()

    # Configure root logger
    root = logging.getLogger()
    root.setLevel(logging.INFO)

    # Remove existing handlers to avoid duplicates
    root.handlers.clear()

    # TimedRotatingFileHandler - rotates at midnight, keeps 1 day
    file_handler = TimedRotatingFileHandler(
        LOGS_DIR / "server.log",
        when="midnight",
        interval=1,
        backupCount=1,  # Keep only 1 backup (24h worth)
    )
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s [%(name)s] %(levelname)s: %(message)s")
    )
    root.addHandler(file_handler)

    # Keep console output
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    root.addHandler(console_handler)

    logging.info("Logging initialized (24h retention at %s)", LOGS_DIR)
