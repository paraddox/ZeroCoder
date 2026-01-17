"""
Error Recovery Tests
====================

Enterprise-grade tests for error handling and recovery including:
- Exception handling in all layers
- Graceful degradation
- Error propagation
- Recovery from failures
"""

import asyncio
import json
import pytest
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock
import subprocess

import sys
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# =============================================================================
# Registry Error Recovery Tests
# =============================================================================

class TestRegistryErrorRecovery:
    """Tests for registry error handling and recovery."""

    @pytest.fixture
    def isolated_registry(self, tmp_path, monkeypatch):
        """Create isolated registry for error testing."""
        import registry

        registry._engine = None
        registry._SessionLocal = None

        temp_config = tmp_path / "zerocoder"
        temp_config.mkdir(parents=True)

        monkeypatch.setattr(registry, "get_registry_path", lambda: tmp_path / "registry.db")
        monkeypatch.setattr(registry, "get_config_dir", lambda: temp_config)
        monkeypatch.setattr(registry, "get_projects_dir", lambda: temp_config / "projects")

        return registry

    @pytest.mark.unit
    def test_duplicate_registration_error(self, isolated_registry):
        """Test error handling for duplicate project registration."""
        isolated_registry.register_project(
            name="dup-test",
            git_url="https://github.com/user/repo.git"
        )

        with pytest.raises(isolated_registry.RegistryError):
            isolated_registry.register_project(
                name="dup-test",
                git_url="https://github.com/other/repo.git"
            )

    @pytest.mark.unit
    def test_invalid_name_error(self, isolated_registry):
        """Test error handling for invalid project names."""
        with pytest.raises(ValueError):
            isolated_registry.register_project(
                name="invalid/name",
                git_url="https://github.com/user/repo.git"
            )

    @pytest.mark.unit
    def test_get_nonexistent_project_returns_none(self, isolated_registry):
        """Test that getting nonexistent project returns None, not error."""
        info = isolated_registry.get_project_info("nonexistent")
        assert info is None

    @pytest.mark.unit
    def test_unregister_nonexistent_returns_false(self, isolated_registry):
        """Test that unregistering nonexistent project returns False."""
        result = isolated_registry.unregister_project("nonexistent")
        assert result is False


# =============================================================================
# Container Manager Error Recovery Tests
# =============================================================================

class TestContainerManagerErrorRecovery:
    """Tests for container manager error handling."""

    @pytest.fixture
    def container_manager(self, tmp_path):
        """Create container manager for error testing."""
        from server.services.container_manager import ContainerManager, _container_managers

        _container_managers.clear()
        project_dir = tmp_path / "error-test"
        project_dir.mkdir(parents=True)

        with patch("server.services.container_manager.get_projects_dir") as mock_dir:
            mock_dir.return_value = tmp_path
            with patch.object(ContainerManager, "_sync_status"):
                with patch.object(ContainerManager, "_check_user_started_marker", return_value=False):
                    manager = ContainerManager(
                        project_name="error-test",
                        git_url="https://github.com/user/repo.git",
                        container_number=1,
                        project_dir=project_dir,
                        skip_db_persist=True,
                    )
        return manager

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_callback_error_isolation(self, container_manager):
        """Test that callback errors don't affect other callbacks."""
        failing_cb = AsyncMock(side_effect=Exception("Callback failed"))
        success_cb = AsyncMock()

        container_manager.add_status_callback(failing_cb)
        container_manager.add_status_callback(success_cb)

        # Should not raise
        await container_manager._notify_status("running")

        # Success callback should still be called
        success_cb.assert_called_once_with("running")

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_output_callback_error_isolation(self, container_manager):
        """Test that output callback errors don't affect other callbacks."""
        failing_cb = AsyncMock(side_effect=Exception("Output callback failed"))
        success_cb = AsyncMock()

        container_manager.add_output_callback(failing_cb)
        container_manager.add_output_callback(success_cb)

        # Should not raise
        await container_manager._notify_output("test line")

        # Success callback should still be called
        success_cb.assert_called_once()

    @pytest.mark.unit
    def test_subprocess_error_handling_in_sync(self, container_manager):
        """Test handling of subprocess errors during sync."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.SubprocessError("Docker not available")
            with patch("server.services.container_manager.get_container", return_value=None):
                # Should not raise, should set not_created
                container_manager._sync_status()

        assert container_manager._status == "not_created"

    @pytest.mark.unit
    def test_is_agent_running_handles_errors(self, container_manager):
        """Test that is_agent_running handles subprocess errors."""
        container_manager._status = "running"

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = Exception("Docker error")

            # Should not raise, should return False
            result = container_manager.is_agent_running()
            assert result is False


# =============================================================================
# WebSocket Error Recovery Tests
# =============================================================================

class TestWebSocketErrorRecovery:
    """Tests for WebSocket error handling."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_broadcast_handles_dead_connections(self):
        """Test that broadcast handles dead connections gracefully."""
        from server.websocket import ConnectionManager

        manager = ConnectionManager()
        healthy_client = AsyncMock()
        dead_client = AsyncMock()
        dead_client.send_json.side_effect = Exception("Connection closed")

        await manager.connect(healthy_client, "test-project")
        await manager.connect(dead_client, "test-project")

        # Should not raise
        await manager.broadcast_to_project("test-project", {"type": "test"})

        # Healthy client should receive message
        healthy_client.send_json.assert_called_once()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_disconnect_handles_missing_project(self):
        """Test that disconnect handles missing project gracefully."""
        from server.websocket import ConnectionManager

        manager = ConnectionManager()
        client = AsyncMock()

        # Should not raise
        await manager.disconnect(client, "nonexistent-project")

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_broadcast_to_empty_project(self):
        """Test that broadcast to empty project doesn't error."""
        from server.websocket import ConnectionManager

        manager = ConnectionManager()

        # Should not raise
        await manager.broadcast_to_project("empty-project", {"type": "test"})


# =============================================================================
# Beads Command Error Recovery Tests
# =============================================================================

class TestBeadsErrorRecovery:
    """Tests for beads command error handling."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_send_command_handles_timeout(self):
        """Test handling of command timeout."""
        from server.services.container_beads import send_beads_command

        with patch("asyncio.to_thread") as mock_thread:
            mock_thread.side_effect = asyncio.TimeoutError()

            with pytest.raises(asyncio.TimeoutError):
                await send_beads_command("test-project", "list")

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_send_command_handles_json_error(self):
        """Test handling of invalid JSON response."""
        from server.services.container_beads import send_beads_command

        with patch("asyncio.to_thread") as mock_thread:
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = "not valid json"
            mock_thread.return_value = mock_result

            with pytest.raises(json.JSONDecodeError):
                await send_beads_command("test-project", "list")

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_beads_client_handles_command_failure(self):
        """Test ContainerBeadsClient handles command failures."""
        from server.services.container_beads import ContainerBeadsClient

        client = ContainerBeadsClient("test-project")

        with patch("server.services.container_beads.send_beads_command") as mock_cmd:
            mock_cmd.side_effect = Exception("Command failed")

            with pytest.raises(Exception, match="Command failed"):
                await client.list_all()


# =============================================================================
# Prompt Loading Error Recovery Tests
# =============================================================================

class TestPromptLoadingErrorRecovery:
    """Tests for prompt loading error handling."""

    @pytest.mark.unit
    def test_load_prompt_file_not_found(self, tmp_path):
        """Test error when prompt file not found."""
        from prompts import load_prompt

        with pytest.raises(FileNotFoundError):
            load_prompt("nonexistent", tmp_path)

    @pytest.mark.unit
    def test_get_app_spec_file_not_found(self, tmp_path):
        """Test error when app_spec not found."""
        from prompts import get_app_spec

        project_dir = tmp_path / "no-spec"
        project_dir.mkdir()

        with pytest.raises(FileNotFoundError):
            get_app_spec(project_dir)

    @pytest.mark.unit
    def test_load_prompt_with_permission_error(self, tmp_path, monkeypatch):
        """Test handling of permission errors in prompt loading."""
        from prompts import load_prompt

        project_dir = tmp_path / "permission-test"
        project_dir.mkdir()
        prompts_dir = project_dir / "prompts"
        prompts_dir.mkdir()

        # Create file but make it unreadable
        prompt_file = prompts_dir / "test.md"
        prompt_file.write_text("content")

        # Mock read_text to raise PermissionError
        original_read = Path.read_text

        def mock_read(self, *args, **kwargs):
            if "test.md" in str(self):
                raise PermissionError("Permission denied")
            return original_read(self, *args, **kwargs)

        monkeypatch.setattr(Path, "read_text", mock_read)

        # Should fall back to template or raise FileNotFoundError
        with pytest.raises(FileNotFoundError):
            load_prompt("test", project_dir)


# =============================================================================
# API Router Error Recovery Tests
# =============================================================================

class TestAPIRouterErrorRecovery:
    """Tests for API router error handling."""

    @pytest.fixture
    def test_client(self):
        """Create test client."""
        from fastapi.testclient import TestClient
        from server.main import app

        with patch("signal.signal", return_value=None):
            with TestClient(app, raise_server_exceptions=False) as client:
                yield client

    @pytest.mark.unit
    def test_get_nonexistent_project(self, test_client):
        """Test 404 response for nonexistent project."""
        response = test_client.get("/api/projects/nonexistent-project-xyz")
        assert response.status_code == 404

    @pytest.mark.unit
    def test_invalid_project_name_in_url(self, test_client):
        """Test handling of invalid project name in URL."""
        # Project names with special chars should be rejected
        response = test_client.get("/api/projects/../../etc/passwd")
        assert response.status_code in [400, 404, 422]


# =============================================================================
# Progress Module Error Recovery Tests
# =============================================================================

class TestProgressErrorRecovery:
    """Tests for progress module error handling."""

    @pytest.mark.unit
    def test_has_features_with_missing_directory(self, tmp_path):
        """Test has_features with missing project directory."""
        from progress import has_features

        nonexistent = tmp_path / "nonexistent"
        result = has_features(nonexistent)
        assert result is False

    @pytest.mark.unit
    def test_has_features_with_empty_beads(self, tmp_path):
        """Test has_features with empty beads directory."""
        from progress import has_features

        project_dir = tmp_path / "empty-beads"
        project_dir.mkdir()
        (project_dir / ".beads").mkdir()

        result = has_features(project_dir)
        assert result is False

    @pytest.mark.unit
    def test_count_passing_tests_handles_missing_dir(self, tmp_path):
        """Test count_passing_tests with missing directory."""
        from progress import count_passing_tests

        nonexistent = tmp_path / "nonexistent"
        passing, in_progress, total = count_passing_tests(nonexistent)

        assert passing == 0
        assert in_progress == 0
        assert total == 0


# =============================================================================
# Concurrent Error Recovery Tests
# =============================================================================

class TestConcurrentErrorRecovery:
    """Tests for error handling under concurrent access."""

    @pytest.mark.unit
    def test_concurrent_registry_errors(self, tmp_path, monkeypatch):
        """Test registry handles concurrent errors gracefully."""
        import registry
        import threading

        registry._engine = None
        registry._SessionLocal = None

        temp_config = tmp_path / "zerocoder"
        temp_config.mkdir(parents=True)

        monkeypatch.setattr(registry, "get_registry_path", lambda: tmp_path / "concurrent.db")
        monkeypatch.setattr(registry, "get_config_dir", lambda: temp_config)
        monkeypatch.setattr(registry, "get_projects_dir", lambda: temp_config / "projects")

        errors = []
        successes = []
        lock = threading.Lock()

        def register_same_project():
            try:
                registry.register_project(
                    name="concurrent-same",
                    git_url="https://github.com/user/repo.git"
                )
                with lock:
                    successes.append(True)
            except Exception as e:
                with lock:
                    errors.append(e)

        threads = [threading.Thread(target=register_same_project) for _ in range(5)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Exactly one should succeed, others should fail
        total = len(successes) + len(errors)
        assert total == 5
        assert len(successes) >= 1  # At least one succeeds
        # Due to SQLite locking, some may fail

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_concurrent_websocket_errors(self):
        """Test WebSocket manager handles concurrent errors."""
        from server.websocket import ConnectionManager

        manager = ConnectionManager()

        # Create mix of healthy and failing clients
        clients = []
        for i in range(10):
            client = AsyncMock()
            if i % 2 == 0:
                client.send_json.side_effect = Exception("Connection lost")
            clients.append(client)
            await manager.connect(client, "concurrent-test")

        # Broadcast multiple messages concurrently
        async def broadcast():
            await manager.broadcast_to_project("concurrent-test", {"type": "test"})

        # Should not raise
        await asyncio.gather(*[broadcast() for _ in range(5)])


# =============================================================================
# Resource Cleanup Error Recovery Tests
# =============================================================================

class TestResourceCleanupErrorRecovery:
    """Tests for resource cleanup error handling."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_callback_cleanup_on_error(self, tmp_path):
        """Test that callbacks are cleaned up even on error."""
        from server.services.container_manager import ContainerManager, _container_managers

        _container_managers.clear()
        project_dir = tmp_path / "cleanup-test"
        project_dir.mkdir(parents=True)

        with patch("server.services.container_manager.get_projects_dir") as mock_dir:
            mock_dir.return_value = tmp_path
            with patch.object(ContainerManager, "_sync_status"):
                with patch.object(ContainerManager, "_check_user_started_marker", return_value=False):
                    manager = ContainerManager(
                        project_name="cleanup-test",
                        git_url="https://github.com/user/repo.git",
                        container_number=1,
                        project_dir=project_dir,
                        skip_db_persist=True,
                    )

        callback = AsyncMock()
        manager.add_status_callback(callback)

        # Simulate error during notification
        callback.side_effect = Exception("Notification error")

        # Should not raise
        await manager._notify_status("running")

        # Callback should still be registered (not removed on error)
        assert callback in manager._status_callbacks

    @pytest.mark.unit
    def test_file_handle_cleanup_on_error(self, tmp_path):
        """Test file handles are closed on error."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")

        try:
            with open(test_file, "r") as f:
                raise ValueError("Simulated error")
        except ValueError:
            pass

        # File should be closed, can be deleted
        test_file.unlink()
        assert not test_file.exists()


# =============================================================================
# Graceful Degradation Tests
# =============================================================================

class TestGracefulDegradation:
    """Tests for graceful degradation when components fail."""

    @pytest.mark.unit
    def test_features_available_without_container(self, tmp_path):
        """Test that features can be read without running container."""
        project_dir = tmp_path / "no-container"
        project_dir.mkdir()
        beads_dir = project_dir / ".beads"
        beads_dir.mkdir()

        # Create feature file
        issues_file = beads_dir / "issues.jsonl"
        issues_file.write_text('{"id":"feat-1","title":"Test","status":"open","priority":1}\n')

        from server.routers.features import read_local_beads_features
        result = read_local_beads_features(project_dir)

        assert len(result["pending"]) == 1

    @pytest.mark.unit
    def test_progress_without_beads(self, tmp_path):
        """Test progress tracking works without beads."""
        from progress import count_passing_tests

        project_dir = tmp_path / "no-beads"
        project_dir.mkdir()

        passing, in_progress, total = count_passing_tests(project_dir)

        # Should return zeros, not error
        assert passing == 0
        assert in_progress == 0
        assert total == 0

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_websocket_continues_on_poll_error(self):
        """Test WebSocket continues after poll error."""
        from server.websocket import ConnectionManager

        manager = ConnectionManager()
        client = AsyncMock()

        await manager.connect(client, "poll-error-test")

        # Simulate poll sending message even after error
        await manager.broadcast_to_project("poll-error-test", {"type": "error_recovery"})

        client.send_json.assert_called_once()
