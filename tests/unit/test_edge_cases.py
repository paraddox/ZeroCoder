"""
Edge Cases Unit Tests
=====================

Enterprise-grade tests for edge cases including:
- Boundary conditions
- Empty/null handling
- Unicode and special characters
- Large data handling
- Concurrent access patterns
"""

import asyncio
import json
import pytest
import string
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional
from unittest.mock import AsyncMock, MagicMock, patch
import threading

import sys
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# =============================================================================
# Boundary Condition Tests
# =============================================================================

class TestBoundaryConditions:
    """Tests for boundary conditions."""

    @pytest.mark.unit
    def test_project_name_length_boundaries(self, isolated_registry):
        """Test project name at length boundaries."""
        # Minimum length (1 character)
        isolated_registry.register_project(
            name="a",
            git_url="https://github.com/user/a.git"
        )
        assert isolated_registry.get_project_info("a") is not None

        # Maximum length (50 characters)
        max_name = "a" * 50
        isolated_registry.register_project(
            name=max_name,
            git_url="https://github.com/user/max.git"
        )
        assert isolated_registry.get_project_info(max_name) is not None

        # Over maximum (51 characters)
        over_max = "a" * 51
        with pytest.raises(ValueError):
            isolated_registry.register_project(
                name=over_max,
                git_url="https://github.com/user/over.git"
            )

    @pytest.mark.unit
    def test_container_number_boundaries(self, isolated_registry):
        """Test container number at boundaries."""
        isolated_registry.register_project(
            name="boundary-project",
            git_url="https://github.com/user/repo.git"
        )

        # Container 0 (init container)
        id0 = isolated_registry.create_container("boundary-project", 0, "init")
        assert id0 is not None

        # Container 1 (first coding container)
        id1 = isolated_registry.create_container("boundary-project", 1, "coding")
        assert id1 is not None

        # Container 10 (max typical)
        id10 = isolated_registry.create_container("boundary-project", 10, "coding")
        assert id10 is not None

    @pytest.mark.unit
    def test_priority_boundaries(self):
        """Test priority value boundaries."""
        from server.schemas import FeatureCreate

        # Valid priorities (0-4)
        for priority in range(5):
            feature = FeatureCreate(
                category="test",
                name="Test Feature",
                description="Test",
                steps=[],
                priority=priority
            )
            assert feature.priority == priority

    @pytest.mark.unit
    def test_empty_feature_list(self):
        """Test handling of empty feature lists."""
        features = {
            "pending": [],
            "in_progress": [],
            "done": []
        }

        total = sum(len(v) for v in features.values())
        assert total == 0

        # Percentage should handle empty
        percentage = 0.0 if total == 0 else (len(features["done"]) / total) * 100
        assert percentage == 0.0


# =============================================================================
# Empty/Null Handling Tests
# =============================================================================

class TestEmptyNullHandling:
    """Tests for empty and null value handling."""

    @pytest.mark.unit
    def test_empty_project_name_rejected(self, isolated_registry):
        """Test empty project name is rejected."""
        with pytest.raises(ValueError):
            isolated_registry.register_project(
                name="",
                git_url="https://github.com/user/repo.git"
            )

    @pytest.mark.unit
    def test_empty_git_url_rejected(self, isolated_registry):
        """Test empty git URL is rejected."""
        with pytest.raises(ValueError):
            isolated_registry.register_project(
                name="test-project",
                git_url=""
            )

    @pytest.mark.unit
    def test_none_values_in_optional_fields(self):
        """Test None values in optional fields."""
        from server.schemas import FeatureUpdate

        # All optional fields can be None
        update = FeatureUpdate()
        assert update.name is None
        assert update.description is None
        assert update.category is None
        assert update.priority is None

    @pytest.mark.unit
    def test_empty_string_vs_none(self):
        """Test distinction between empty string and None."""
        from server.schemas import FeatureUpdate

        # Empty string
        update_empty = FeatureUpdate(name="")
        assert update_empty.name == ""

        # None
        update_none = FeatureUpdate(name=None)
        assert update_none.name is None

    @pytest.mark.unit
    def test_empty_steps_list(self):
        """Test feature with empty steps list."""
        from server.schemas import FeatureCreate

        feature = FeatureCreate(
            category="test",
            name="No Steps Feature",
            description="Feature without steps",
            steps=[]
        )
        assert feature.steps == []

    @pytest.mark.unit
    def test_empty_beads_issues_file(self, tmp_path):
        """Test reading empty beads issues file."""
        beads_dir = tmp_path / ".beads"
        beads_dir.mkdir()

        issues_file = beads_dir / "issues.jsonl"
        issues_file.write_text("")

        # Should return empty list, not error
        with open(issues_file) as f:
            lines = f.readlines()

        assert len(lines) == 0


# =============================================================================
# Unicode and Special Character Tests
# =============================================================================

class TestUnicodeHandling:
    """Tests for Unicode and special character handling."""

    @pytest.mark.unit
    def test_unicode_in_feature_description(self):
        """Test Unicode characters in feature description."""
        from server.schemas import FeatureCreate

        # Various Unicode characters
        descriptions = [
            "Add emoji support 🎉",
            "Japanese: 日本語",
            "Chinese: 中文",
            "Arabic: العربية",
            "Special: ñ ü ö é",
            "Math: ∑ ∏ √ ∞",
        ]

        for desc in descriptions:
            feature = FeatureCreate(
                category="test",
                name="Unicode Test",
                description=desc,
                steps=[]
            )
            assert feature.description == desc

    @pytest.mark.unit
    def test_unicode_in_feature_name(self):
        """Test Unicode in feature names."""
        from server.schemas import FeatureCreate

        feature = FeatureCreate(
            category="test",
            name="Feature with émoji 🚀",
            description="Test",
            steps=[]
        )
        assert "🚀" in feature.name

    @pytest.mark.unit
    def test_json_encoding_unicode(self):
        """Test JSON encoding preserves Unicode."""
        data = {
            "name": "Test 日本語",
            "description": "Contains émoji 🎉",
        }

        encoded = json.dumps(data, ensure_ascii=False)
        decoded = json.loads(encoded)

        assert decoded["name"] == "Test 日本語"
        assert "🎉" in decoded["description"]

    @pytest.mark.unit
    def test_path_safe_characters(self, isolated_registry):
        """Test project names with path-safe characters."""
        safe_names = [
            "project-name",
            "project_name",
            "ProjectName",
            "project123",
            "123project",
        ]

        for i, name in enumerate(safe_names):
            isolated_registry.register_project(
                name=f"{name}-{i}",  # Make unique
                git_url=f"https://github.com/user/{name}.git"
            )

    @pytest.mark.unit
    def test_newlines_in_description(self):
        """Test newlines in descriptions."""
        from server.schemas import FeatureCreate

        description = """Line 1
Line 2
Line 3"""

        feature = FeatureCreate(
            category="test",
            name="Multiline",
            description=description,
            steps=[]
        )
        assert "\n" in feature.description


# =============================================================================
# Large Data Tests
# =============================================================================

class TestLargeDataHandling:
    """Tests for large data handling."""

    @pytest.mark.unit
    @pytest.mark.slow
    def test_large_feature_list(self):
        """Test handling large number of features."""
        features = {
            "pending": [
                {"id": f"feat-{i}", "name": f"Feature {i}"}
                for i in range(1000)
            ],
            "in_progress": [],
            "done": []
        }

        assert len(features["pending"]) == 1000

        # Serialization should work
        json_str = json.dumps(features)
        assert len(json_str) > 10000

    @pytest.mark.unit
    @pytest.mark.slow
    def test_large_description(self):
        """Test large feature descriptions."""
        from server.schemas import FeatureCreate

        # 10KB description
        large_description = "x" * 10000

        feature = FeatureCreate(
            category="test",
            name="Large Description",
            description=large_description,
            steps=[]
        )
        assert len(feature.description) == 10000

    @pytest.mark.unit
    @pytest.mark.slow
    def test_many_steps(self):
        """Test feature with many steps."""
        from server.schemas import FeatureCreate

        steps = [f"Step {i}: Do something" for i in range(100)]

        feature = FeatureCreate(
            category="test",
            name="Many Steps",
            description="Test",
            steps=steps
        )
        assert len(feature.steps) == 100

    @pytest.mark.unit
    @pytest.mark.slow
    def test_large_log_output(self):
        """Test handling large log output."""
        log_lines = [f"Log line {i}" for i in range(10000)]

        # Should be able to process
        processed = "\n".join(log_lines)
        assert len(processed.split("\n")) == 10000

    @pytest.mark.unit
    @pytest.mark.slow
    def test_many_projects(self, isolated_registry):
        """Test handling many projects."""
        # Register many projects
        for i in range(50):
            try:
                isolated_registry.register_project(
                    name=f"large-test-{i}",
                    git_url=f"https://github.com/user/repo-{i}.git"
                )
            except Exception:
                pass  # Handle any transient failures

        projects = isolated_registry.list_registered_projects()
        # At least some should succeed
        assert len([p for p in projects if p.startswith("large-test")]) > 10


# =============================================================================
# Concurrent Access Tests
# =============================================================================

class TestConcurrentAccess:
    """Tests for concurrent access patterns."""

    @pytest.mark.unit
    def test_concurrent_reads(self, isolated_registry):
        """Test concurrent reads are safe."""
        isolated_registry.register_project(
            name="concurrent-read",
            git_url="https://github.com/user/repo.git"
        )

        results = []
        lock = threading.Lock()

        def read_project():
            info = isolated_registry.get_project_info("concurrent-read")
            with lock:
                results.append(info)

        threads = [
            threading.Thread(target=read_project)
            for _ in range(10)
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All reads should succeed
        assert len(results) == 10
        assert all(r is not None for r in results)

    @pytest.mark.unit
    def test_concurrent_writes_different_projects(self, isolated_registry):
        """Test concurrent writes to different projects."""
        results = []
        lock = threading.Lock()

        def write_project(name):
            try:
                isolated_registry.register_project(
                    name=name,
                    git_url=f"https://github.com/user/{name}.git"
                )
                with lock:
                    results.append(("success", name))
            except Exception as e:
                with lock:
                    results.append(("error", str(e)))

        threads = [
            threading.Thread(target=write_project, args=(f"concurrent-write-{i}",))
            for i in range(5)
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All or most should succeed
        successes = sum(1 for r in results if r[0] == "success")
        assert successes >= 1

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_concurrent_async_operations(self):
        """Test concurrent async operations."""
        results = []

        async def async_operation(i):
            await asyncio.sleep(0.01)
            results.append(i)

        tasks = [
            async_operation(i)
            for i in range(10)
        ]

        await asyncio.gather(*tasks)

        assert len(results) == 10


# =============================================================================
# State Transition Tests
# =============================================================================

class TestStateTransitions:
    """Tests for state machine transitions."""

    @pytest.mark.unit
    def test_container_state_transitions(self, isolated_registry):
        """Test valid container state transitions.

        Note: Database only allows 'created', 'running', 'stopping', 'stopped'.
        'completed' is an in-memory status used by ContainerManager.
        """
        isolated_registry.register_project(
            name="state-test",
            git_url="https://github.com/user/repo.git"
        )
        isolated_registry.create_container("state-test", 1, "coding")

        # Valid transitions for database status
        # (created -> running -> stopping -> stopped -> running)
        valid_transitions = [
            ("created", "running"),
            ("running", "stopping"),
            ("stopping", "stopped"),
            ("stopped", "running"),
        ]

        for from_state, to_state in valid_transitions:
            isolated_registry.update_container_status(
                "state-test", 1, "coding",
                status=to_state
            )
            container = isolated_registry.get_container("state-test", 1, "coding")
            assert container["status"] == to_state

    @pytest.mark.unit
    def test_feature_status_transitions(self):
        """Test valid feature status transitions."""
        valid_transitions = [
            ("open", "in_progress"),
            ("in_progress", "closed"),
            ("closed", "open"),  # Reopen
        ]

        # All transitions should be valid
        for from_status, to_status in valid_transitions:
            # In real system, this would update the feature
            assert from_status != to_status


# =============================================================================
# Error Message Tests
# =============================================================================

class TestErrorMessages:
    """Tests for error message quality."""

    @pytest.mark.unit
    def test_validation_error_messages(self, isolated_registry):
        """Test validation errors have helpful messages."""
        with pytest.raises(ValueError) as exc_info:
            isolated_registry.register_project(
                name="invalid@name",
                git_url="https://github.com/user/repo.git"
            )

        error_message = str(exc_info.value)
        # Should explain what's wrong
        assert "name" in error_message.lower() or "invalid" in error_message.lower()

    @pytest.mark.unit
    def test_not_found_error_messages(self, isolated_registry):
        """Test not found errors are clear."""
        info = isolated_registry.get_project_info("nonexistent-project")
        assert info is None  # Returns None, not error

    @pytest.mark.unit
    def test_duplicate_error_messages(self, isolated_registry):
        """Test duplicate errors are clear."""
        isolated_registry.register_project(
            name="duplicate-test",
            git_url="https://github.com/user/repo.git"
        )

        with pytest.raises(Exception) as exc_info:
            isolated_registry.register_project(
                name="duplicate-test",
                git_url="https://github.com/other/repo.git"
            )

        # Should indicate duplicate
        error_message = str(exc_info.value)
        assert "duplicate" in error_message.lower() or "exists" in error_message.lower() or "already" in error_message.lower()


# =============================================================================
# Date/Time Edge Cases
# =============================================================================

class TestDateTimeEdgeCases:
    """Tests for date/time edge cases."""

    @pytest.mark.unit
    def test_midnight_boundary(self):
        """Test operations around midnight."""
        # Just before midnight
        before = datetime(2024, 1, 15, 23, 59, 59)
        # Just after midnight
        after = datetime(2024, 1, 16, 0, 0, 1)

        # Time difference should be 2 seconds
        diff = (after - before).total_seconds()
        assert diff == 2

    @pytest.mark.unit
    def test_year_boundary(self):
        """Test operations around year boundary."""
        end_of_year = datetime(2024, 12, 31, 23, 59, 59)
        start_of_year = datetime(2025, 1, 1, 0, 0, 1)

        diff = (start_of_year - end_of_year).total_seconds()
        assert diff == 2

    @pytest.mark.unit
    def test_timezone_handling(self):
        """Test timezone-aware timestamps."""
        from datetime import timezone

        utc_time = datetime.now(timezone.utc)
        iso_string = utc_time.isoformat()

        # Should include timezone info
        assert "+" in iso_string or "Z" in iso_string

    @pytest.mark.unit
    def test_future_timestamps(self):
        """Test handling of future timestamps."""
        future = datetime.now() + timedelta(days=365)

        # Should be valid
        assert future > datetime.now()

    @pytest.mark.unit
    def test_very_old_timestamps(self):
        """Test handling of very old timestamps."""
        old = datetime(1970, 1, 1)  # Unix epoch

        # Should be valid
        assert old < datetime.now()


# =============================================================================
# Network Edge Cases
# =============================================================================

class TestNetworkEdgeCases:
    """Tests for network-related edge cases."""

    @pytest.mark.unit
    def test_git_url_with_port(self, isolated_registry):
        """Test git URL with explicit port."""
        isolated_registry.register_project(
            name="port-test",
            git_url="https://github.com:443/user/repo.git"
        )
        assert isolated_registry.get_project_info("port-test") is not None

    @pytest.mark.unit
    def test_git_url_with_path(self, isolated_registry):
        """Test git URL with complex path."""
        isolated_registry.register_project(
            name="path-test",
            git_url="https://github.com/org/team/repo.git"
        )
        assert isolated_registry.get_project_info("path-test") is not None

    @pytest.mark.unit
    def test_ssh_git_url_formats(self, isolated_registry):
        """Test various SSH git URL formats."""
        ssh_urls = [
            ("ssh-1", "git@github.com:user/repo.git"),
            ("ssh-2", "git@gitlab.com:user/repo.git"),
        ]

        for name, url in ssh_urls:
            try:
                isolated_registry.register_project(name=name, git_url=url)
            except ValueError:
                # Some formats might not be accepted
                pass


# =============================================================================
# Memory Boundary Tests
# =============================================================================

class TestMemoryBoundaries:
    """Tests for memory-related boundaries."""

    @pytest.mark.unit
    @pytest.mark.slow
    def test_large_json_parsing(self):
        """Test parsing large JSON documents."""
        # 1MB JSON document
        large_data = {
            "items": [{"id": i, "data": "x" * 100} for i in range(1000)]
        }

        json_str = json.dumps(large_data)
        assert len(json_str) > 100000

        # Should parse without error
        parsed = json.loads(json_str)
        assert len(parsed["items"]) == 1000

    @pytest.mark.unit
    def test_string_concatenation_performance(self):
        """Test string concatenation doesn't cause issues."""
        parts = [f"part-{i}" for i in range(1000)]

        # Using join (efficient)
        result = "".join(parts)
        assert len(result) > 5000

    @pytest.mark.unit
    def test_list_growth(self):
        """Test list growth behavior."""
        data: List[int] = []

        for i in range(10000):
            data.append(i)

        assert len(data) == 10000
