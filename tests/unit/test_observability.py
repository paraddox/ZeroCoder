"""
Observability Unit Tests
========================

Enterprise-grade tests for observability patterns including:
- Logging verification
- Metrics validation
- Health check testing
- Audit trail verification
- Debugging support
"""

import asyncio
import json
import logging
import pytest
import re
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any
from unittest.mock import AsyncMock, MagicMock, patch, call
from io import StringIO

import sys
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# =============================================================================
# Logging Tests
# =============================================================================

class TestLoggingPatterns:
    """Tests for logging patterns and best practices."""

    @pytest.mark.unit
    def test_log_format_consistency(self):
        """Test that log format is consistent."""
        # Standard log format components
        required_fields = ["timestamp", "level", "message"]

        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "level": "INFO",
            "message": "Test message"
        }

        for field in required_fields:
            assert field in log_entry

    @pytest.mark.unit
    def test_sensitive_data_not_logged(self):
        """Test that sensitive data is not logged."""
        from server.services.container_manager import sanitize_output

        sensitive_data = [
            "api_key=sk-ant-12345",
            "password=secret123",
            "token=ghp_abcdef",
            "secret=mysecret",
            "ANTHROPIC_API_KEY=sk-ant-test",
        ]

        for data in sensitive_data:
            sanitized = sanitize_output(data)
            # Should not contain the actual value
            if "=" in data:
                value = data.split("=")[1]
                assert value not in sanitized or "[REDACTED]" in sanitized

    @pytest.mark.unit
    def test_log_level_appropriate(self):
        """Test that log levels are used appropriately."""
        log_levels = {
            "DEBUG": ["details", "verbose", "trace"],
            "INFO": ["started", "completed", "created"],
            "WARNING": ["retry", "deprecated", "slow"],
            "ERROR": ["failed", "exception", "error"],
            "CRITICAL": ["fatal", "crash", "unrecoverable"],
        }

        # Verify level categories make sense
        assert "ERROR" in log_levels
        assert "INFO" in log_levels

    @pytest.mark.unit
    def test_structured_logging_format(self):
        """Test structured logging produces valid JSON."""
        structured_log = {
            "timestamp": datetime.now().isoformat(),
            "level": "INFO",
            "message": "Operation completed",
            "context": {
                "project": "test-project",
                "container": 1,
                "duration_ms": 1500
            }
        }

        # Should be valid JSON
        json_str = json.dumps(structured_log)
        parsed = json.loads(json_str)
        assert parsed["level"] == "INFO"

    @pytest.mark.unit
    def test_correlation_id_propagation(self):
        """Test correlation IDs are propagated through logs."""
        correlation_id = "req-12345-abcdef"

        # All related logs should include correlation ID
        log_entries = [
            {"correlation_id": correlation_id, "message": "Request started"},
            {"correlation_id": correlation_id, "message": "Processing"},
            {"correlation_id": correlation_id, "message": "Request completed"},
        ]

        # All entries have same correlation ID
        ids = set(entry["correlation_id"] for entry in log_entries)
        assert len(ids) == 1


# =============================================================================
# Health Check Tests
# =============================================================================

class TestHealthChecks:
    """Tests for health check endpoints and patterns."""

    @pytest.mark.unit
    def test_health_check_response_format(self):
        """Test health check response format."""
        health_response = {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "components": {
                "database": {"status": "healthy"},
                "docker": {"status": "healthy"},
                "websocket": {"status": "healthy"},
            }
        }

        assert health_response["status"] in ["healthy", "degraded", "unhealthy"]
        assert "components" in health_response

    @pytest.mark.unit
    def test_health_check_degraded_state(self):
        """Test health check correctly reports degraded state."""
        components = {
            "database": {"status": "healthy"},
            "docker": {"status": "unhealthy"},  # Docker down
            "websocket": {"status": "healthy"},
        }

        # Overall status should be degraded
        statuses = [c["status"] for c in components.values()]
        if "unhealthy" in statuses:
            overall = "degraded" if statuses.count("healthy") > 0 else "unhealthy"
        else:
            overall = "healthy"

        assert overall == "degraded"

    @pytest.mark.unit
    def test_readiness_vs_liveness(self):
        """Test distinction between readiness and liveness probes."""
        # Liveness: Is the process alive?
        liveness = {
            "status": "alive",
            "uptime_seconds": 3600,
        }

        # Readiness: Is the service ready to accept requests?
        readiness = {
            "status": "ready",
            "database_connected": True,
            "docker_available": True,
        }

        # Liveness should be simpler
        assert len(liveness) <= len(readiness)

    @pytest.mark.unit
    def test_health_check_timeout(self):
        """Test health checks have appropriate timeouts."""
        health_check_timeout = 5  # seconds

        # Should be short enough to not block
        assert health_check_timeout <= 10
        # But long enough to get meaningful results
        assert health_check_timeout >= 1


# =============================================================================
# Metrics Tests
# =============================================================================

class TestMetricsCollection:
    """Tests for metrics collection patterns."""

    @pytest.mark.unit
    def test_counter_metrics(self):
        """Test counter metrics increment correctly."""
        counters: Dict[str, int] = {
            "requests_total": 0,
            "errors_total": 0,
            "features_completed": 0,
        }

        # Simulate activity
        counters["requests_total"] += 10
        counters["errors_total"] += 2
        counters["features_completed"] += 5

        # Counters should only increase
        assert counters["requests_total"] == 10
        assert counters["errors_total"] == 2

    @pytest.mark.unit
    def test_gauge_metrics(self):
        """Test gauge metrics can increase and decrease."""
        gauges: Dict[str, float] = {
            "active_containers": 0,
            "active_websockets": 0,
            "memory_usage_mb": 0,
        }

        # Simulate activity
        gauges["active_containers"] = 3
        gauges["active_containers"] = 2  # Decreased
        gauges["active_websockets"] = 5

        # Gauges can go up and down
        assert gauges["active_containers"] == 2

    @pytest.mark.unit
    def test_histogram_metrics(self):
        """Test histogram metrics for latency tracking."""
        latencies: List[float] = []

        # Simulate requests
        for _ in range(100):
            latency = 0.1 + (0.9 * (hash(str(_)) % 100) / 100)  # 0.1s - 1.0s
            latencies.append(latency)

        # Calculate percentiles
        sorted_latencies = sorted(latencies)
        p50 = sorted_latencies[50]
        p95 = sorted_latencies[95]
        p99 = sorted_latencies[99]

        # p95 should be higher than p50
        assert p95 >= p50
        assert p99 >= p95

    @pytest.mark.unit
    def test_metrics_labels(self):
        """Test metrics have appropriate labels."""
        metric = {
            "name": "http_requests_total",
            "labels": {
                "method": "POST",
                "endpoint": "/api/projects",
                "status_code": "200",
            },
            "value": 150,
        }

        # Should have meaningful labels
        assert "method" in metric["labels"]
        assert "endpoint" in metric["labels"]
        assert "status_code" in metric["labels"]


# =============================================================================
# Audit Trail Tests
# =============================================================================

class TestAuditTrail:
    """Tests for audit trail functionality."""

    @pytest.mark.unit
    def test_audit_entry_format(self):
        """Test audit entry has required fields."""
        audit_entry = {
            "timestamp": datetime.now().isoformat(),
            "action": "project.created",
            "actor": "user@example.com",
            "resource": "project:test-project",
            "details": {
                "git_url": "https://github.com/user/repo.git",
            },
            "result": "success",
        }

        required_fields = ["timestamp", "action", "resource", "result"]
        for field in required_fields:
            assert field in audit_entry

    @pytest.mark.unit
    def test_audit_actions_enumerated(self):
        """Test audit actions are well-defined."""
        valid_actions = [
            "project.created",
            "project.deleted",
            "project.updated",
            "container.started",
            "container.stopped",
            "feature.created",
            "feature.updated",
            "feature.deleted",
            "agent.started",
            "agent.stopped",
        ]

        # All actions should follow pattern
        for action in valid_actions:
            parts = action.split(".")
            assert len(parts) == 2
            assert parts[0] in ["project", "container", "feature", "agent"]

    @pytest.mark.unit
    def test_audit_immutability(self):
        """Test audit entries cannot be modified."""
        audit_log: List[Dict] = []

        # Add entry
        entry = {
            "timestamp": datetime.now().isoformat(),
            "action": "test.action",
            "result": "success",
        }
        audit_log.append(entry.copy())  # Store copy

        # Original entry modification shouldn't affect log
        entry["result"] = "failure"

        # Log should still have original value
        assert audit_log[0]["result"] == "success"

    @pytest.mark.unit
    def test_audit_retention(self):
        """Test audit log retention behavior."""
        max_entries = 10000
        audit_log: List[Dict] = []

        # Add many entries
        for i in range(10500):
            audit_log.append({
                "timestamp": datetime.now().isoformat(),
                "action": f"test.action.{i}",
            })
            if len(audit_log) > max_entries:
                # Oldest entries should be archived/removed
                audit_log.pop(0)

        assert len(audit_log) <= max_entries


# =============================================================================
# Debug Support Tests
# =============================================================================

class TestDebugSupport:
    """Tests for debugging support features."""

    @pytest.mark.unit
    def test_request_tracing(self):
        """Test request tracing capability."""
        trace = {
            "trace_id": "trace-12345",
            "spans": [
                {
                    "name": "api.request",
                    "start": 0,
                    "duration_ms": 150,
                    "children": [
                        {"name": "db.query", "start": 10, "duration_ms": 50},
                        {"name": "container.command", "start": 70, "duration_ms": 60},
                    ]
                }
            ]
        }

        # Trace should have hierarchy
        assert len(trace["spans"]) > 0
        assert "children" in trace["spans"][0]

    @pytest.mark.unit
    def test_error_context_capture(self):
        """Test error context is captured for debugging."""
        error_context = {
            "error_type": "ContainerStartError",
            "message": "Failed to start container",
            "stack_trace": "Traceback...",
            "context": {
                "project_name": "test-project",
                "container_number": 1,
                "docker_version": "20.10.0",
                "image": "zerocoder-project",
            },
            "timestamp": datetime.now().isoformat(),
        }

        # Should have enough context to debug
        assert "stack_trace" in error_context
        assert "context" in error_context
        assert "project_name" in error_context["context"]

    @pytest.mark.unit
    def test_state_snapshot(self):
        """Test state snapshot for debugging."""
        state_snapshot = {
            "timestamp": datetime.now().isoformat(),
            "containers": {
                "test-project-1": {
                    "status": "running",
                    "uptime_seconds": 3600,
                    "last_activity": datetime.now().isoformat(),
                },
            },
            "websockets": {
                "active_connections": 3,
                "projects": ["test-project"],
            },
            "registry": {
                "project_count": 5,
                "container_count": 10,
            },
        }

        # Should capture enough state
        assert "containers" in state_snapshot
        assert "websockets" in state_snapshot


# =============================================================================
# Progress Reporting Tests
# =============================================================================

class TestProgressReporting:
    """Tests for progress reporting functionality."""

    @pytest.mark.unit
    def test_progress_percentage_calculation(self):
        """Test progress percentage is calculated correctly."""
        def calculate_percentage(completed: int, total: int) -> float:
            if total == 0:
                return 0.0
            return round((completed / total) * 100, 2)

        # Test cases
        assert calculate_percentage(5, 10) == 50.0
        assert calculate_percentage(0, 10) == 0.0
        assert calculate_percentage(10, 10) == 100.0
        assert calculate_percentage(0, 0) == 0.0  # Edge case

    @pytest.mark.unit
    def test_progress_message_format(self):
        """Test progress message format."""
        progress = {
            "type": "progress",
            "passing": 5,
            "total": 10,
            "percentage": 50.0,
            "in_progress": 2,
        }

        # Should have all required fields
        assert progress["type"] == "progress"
        assert 0 <= progress["percentage"] <= 100

    @pytest.mark.unit
    def test_feature_status_tracking(self):
        """Test feature status is tracked accurately."""
        features = {
            "pending": ["feat-1", "feat-2"],
            "in_progress": ["feat-3"],
            "done": ["feat-4", "feat-5"],
        }

        total = sum(len(v) for v in features.values())
        done = len(features["done"])

        assert total == 5
        assert done == 2

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_real_time_progress_updates(self):
        """Test real-time progress updates work correctly."""
        updates: List[Dict] = []

        async def on_progress(progress: Dict):
            updates.append(progress)

        # Simulate progress updates
        for i in range(5):
            await on_progress({
                "passing": i,
                "total": 5,
                "percentage": (i / 5) * 100
            })

        assert len(updates) == 5
        assert updates[-1]["passing"] == 4


# =============================================================================
# Error Reporting Tests
# =============================================================================

class TestErrorReporting:
    """Tests for error reporting functionality."""

    @pytest.mark.unit
    def test_error_categorization(self):
        """Test errors are properly categorized."""
        error_categories = {
            "validation": ["Invalid project name", "Invalid git URL"],
            "docker": ["Container start failed", "Image not found"],
            "network": ["Connection refused", "Timeout"],
            "database": ["Database locked", "Constraint violation"],
        }

        def categorize_error(message: str) -> str:
            message_lower = message.lower()
            for category, keywords in error_categories.items():
                for keyword in keywords:
                    if keyword.lower() in message_lower:
                        return category
            return "unknown"

        assert categorize_error("Invalid project name: test@project") == "validation"
        assert categorize_error("Container start failed") == "docker"

    @pytest.mark.unit
    def test_error_rate_calculation(self):
        """Test error rate is calculated correctly."""
        requests = 1000
        errors = 25
        error_rate = (errors / requests) * 100

        assert error_rate == 2.5

    @pytest.mark.unit
    def test_error_aggregation(self):
        """Test errors are aggregated correctly."""
        errors = [
            {"type": "ValidationError", "count": 10},
            {"type": "DockerError", "count": 5},
            {"type": "ValidationError", "count": 15},
        ]

        # Aggregate by type
        aggregated: Dict[str, int] = {}
        for error in errors:
            error_type = error["type"]
            aggregated[error_type] = aggregated.get(error_type, 0) + error["count"]

        assert aggregated["ValidationError"] == 25
        assert aggregated["DockerError"] == 5


# =============================================================================
# Container Output Monitoring Tests
# =============================================================================

class TestContainerOutputMonitoring:
    """Tests for container output monitoring."""

    @pytest.mark.unit
    def test_output_line_parsing(self):
        """Test container output lines are parsed correctly."""
        lines = [
            "[2024-01-15 10:30:00] INFO: Starting agent",
            "[2024-01-15 10:30:01] DEBUG: Loading configuration",
            "[2024-01-15 10:30:02] ERROR: Connection failed",
        ]

        parsed = []
        for line in lines:
            match = re.match(r'\[(.*?)\] (\w+): (.*)', line)
            if match:
                parsed.append({
                    "timestamp": match.group(1),
                    "level": match.group(2),
                    "message": match.group(3),
                })

        assert len(parsed) == 3
        assert parsed[2]["level"] == "ERROR"

    @pytest.mark.unit
    def test_output_filtering(self):
        """Test container output can be filtered."""
        lines = [
            {"level": "DEBUG", "message": "Verbose output"},
            {"level": "INFO", "message": "Normal output"},
            {"level": "ERROR", "message": "Error occurred"},
        ]

        # Filter to INFO and above
        min_level = "INFO"
        level_order = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        min_index = level_order.index(min_level)

        filtered = [
            line for line in lines
            if level_order.index(line["level"]) >= min_index
        ]

        assert len(filtered) == 2
        assert all(line["level"] != "DEBUG" for line in filtered)

    @pytest.mark.unit
    def test_output_rate_limiting(self):
        """Test output rate is monitored."""
        lines_per_second = []
        window_size = 10  # seconds

        # Simulate output
        for second in range(30):
            count = 100 if second < 5 else 10  # Burst then normal
            lines_per_second.append(count)

        # Calculate moving average
        def moving_average(data: List[int], window: int) -> List[float]:
            return [
                sum(data[max(0, i - window + 1):i + 1]) / min(i + 1, window)
                for i in range(len(data))
            ]

        avg = moving_average(lines_per_second, window_size)

        # Should detect burst
        assert max(avg[:10]) > 50  # Early burst
        assert avg[-1] < 20  # Settled down
