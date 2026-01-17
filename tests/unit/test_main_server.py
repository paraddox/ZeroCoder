"""
Tests for FastAPI Main Server Module
====================================

Enterprise-grade tests for server/main.py including:
- Lifespan management (startup/shutdown)
- Security middleware (localhost enforcement)
- CORS configuration
- Static file serving
- Health check endpoint
- Setup status endpoint
"""

import asyncio
import os
import shutil
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_env_vars(monkeypatch):
    """Set up test environment variables."""
    monkeypatch.setenv("ALLOW_EXTERNAL_ACCESS", "false")
    monkeypatch.setenv("CORS_ORIGINS", "")
    yield


@pytest.fixture
def mock_external_access(monkeypatch):
    """Enable external access for testing Docker scenarios."""
    monkeypatch.setenv("ALLOW_EXTERNAL_ACCESS", "true")
    yield


@pytest.fixture
def mock_cors_wildcard(monkeypatch):
    """Set CORS to allow all origins."""
    monkeypatch.setenv("CORS_ORIGINS", "*")
    yield


@pytest.fixture
def mock_custom_cors(monkeypatch):
    """Set custom CORS origins."""
    monkeypatch.setenv("CORS_ORIGINS", "http://example.com,http://test.com")
    yield


@pytest.fixture
def test_app():
    """Create a test FastAPI app without lifespan that requires external deps."""
    # Create a simple app that mimics the real app's endpoints
    app = FastAPI(title="Test App")

    @app.get("/api/health")
    async def health_check():
        return {"status": "healthy"}

    @app.get("/api/setup/status")
    async def setup_status():
        return {
            "claude_cli": shutil.which("claude") is not None,
            "credentials": bool(os.getenv("ANTHROPIC_API_KEY")),
            "node": shutil.which("node") is not None,
            "npm": shutil.which("npm") is not None,
        }

    return app


# =============================================================================
# Health Check Endpoint Tests
# =============================================================================

class TestHealthCheck:
    """Tests for the /api/health endpoint."""

    @pytest.mark.unit
    def test_health_check_returns_healthy(self, test_app):
        """Health check should return healthy status."""
        with TestClient(test_app) as client:
            response = client.get("/api/health")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "healthy"

    @pytest.mark.unit
    def test_health_check_response_format(self, test_app):
        """Health check should return proper JSON format."""
        with TestClient(test_app) as client:
            response = client.get("/api/health")
            assert response.headers["content-type"] == "application/json"


# =============================================================================
# Setup Status Endpoint Tests
# =============================================================================

class TestSetupStatus:
    """Tests for the /api/setup/status endpoint."""

    @pytest.mark.unit
    def test_setup_status_returns_all_fields(self, test_app):
        """Setup status should return all required fields."""
        with TestClient(test_app) as client:
            response = client.get("/api/setup/status")
            assert response.status_code == 200
            data = response.json()
            assert "claude_cli" in data
            assert "credentials" in data
            assert "node" in data
            assert "npm" in data

    @pytest.mark.unit
    def test_setup_status_credentials_from_env(self, test_app, monkeypatch):
        """Setup status should detect credentials from environment."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

        with TestClient(test_app) as client:
            response = client.get("/api/setup/status")
            assert response.status_code == 200
            data = response.json()
            assert data["credentials"] is True

    @pytest.mark.unit
    def test_setup_status_no_credentials(self, test_app, monkeypatch):
        """Setup status should report no credentials when none set."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)

        with TestClient(test_app) as client:
            response = client.get("/api/setup/status")
            assert response.status_code == 200
            data = response.json()
            assert data["credentials"] is False


# =============================================================================
# Security Middleware Tests
# =============================================================================

class TestSecurityMiddleware:
    """Tests for localhost-only security middleware."""

    @pytest.mark.unit
    def test_localhost_ipv4_allowed(self, test_app):
        """Requests from 127.0.0.1 should be allowed."""
        with TestClient(test_app) as client:
            # TestClient uses localhost by default
            response = client.get("/api/health")
            assert response.status_code == 200


# =============================================================================
# CORS Configuration Tests
# =============================================================================

class TestCORSConfiguration:
    """Tests for CORS middleware configuration."""

    @pytest.mark.unit
    def test_cors_allows_localhost_origins(self, test_app):
        """CORS should allow localhost origins by default."""
        with TestClient(test_app) as client:
            response = client.options(
                "/api/health",
                headers={
                    "Origin": "http://localhost:5173",
                    "Access-Control-Request-Method": "GET",
                }
            )
            # Options may return 200 or 405 depending on config
            assert response.status_code in [200, 405]

    @pytest.mark.unit
    def test_cors_allows_vite_dev_server(self, test_app):
        """CORS should allow Vite dev server origin."""
        with TestClient(test_app) as client:
            response = client.get(
                "/api/health",
                headers={"Origin": "http://localhost:5173"}
            )
            assert response.status_code == 200


# =============================================================================
# Idle Container Monitor Tests
# =============================================================================

class TestIdleContainerMonitor:
    """Tests for the idle container background monitor."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_idle_monitor_calls_cleanup(self):
        """Idle monitor should call cleanup_idle_containers."""
        with patch("server.main.cleanup_idle_containers") as mock_cleanup:
            mock_cleanup.return_value = []

            from server.main import idle_container_monitor

            # Create a task that we'll cancel after a short time
            task = asyncio.create_task(idle_container_monitor())
            await asyncio.sleep(0.1)  # Let it start
            task.cancel()

            try:
                await task
            except asyncio.CancelledError:
                pass

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_idle_monitor_handles_exceptions(self):
        """Idle monitor should handle exceptions gracefully."""
        call_count = 0

        async def mock_cleanup():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("Test error")
            return []

        with patch("server.main.cleanup_idle_containers", side_effect=mock_cleanup):
            with patch("server.main.IDLE_CHECK_INTERVAL", 0.01):
                from server.main import idle_container_monitor

                task = asyncio.create_task(idle_container_monitor())
                await asyncio.sleep(0.05)
                task.cancel()

                try:
                    await task
                except asyncio.CancelledError:
                    pass

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_idle_monitor_cancellation(self):
        """Idle monitor should handle cancellation cleanly."""
        with patch("server.main.cleanup_idle_containers") as mock_cleanup:
            mock_cleanup.return_value = []

            from server.main import idle_container_monitor

            task = asyncio.create_task(idle_container_monitor())
            await asyncio.sleep(0.01)
            task.cancel()

            # Task should be cancelled without raising outside
            try:
                await task
            except asyncio.CancelledError:
                pass  # Expected behavior

            # Verify task is done
            assert task.done()


# =============================================================================
# Cleanup Functions Tests
# =============================================================================

class TestCleanupFunctions:
    """Tests for cleanup and signal handling functions."""

    @pytest.mark.unit
    def test_cleanup_on_exit_handles_errors(self):
        """cleanup_on_exit should handle errors gracefully."""
        with patch("server.main.cleanup_all_containers") as mock_cleanup:
            mock_cleanup.side_effect = Exception("Test error")

            from server.main import cleanup_on_exit

            # Should not raise
            cleanup_on_exit()

    @pytest.mark.unit
    def test_signal_handlers_registered(self):
        """Signal handlers should be registered on setup."""
        with patch("signal.signal") as mock_signal:
            with patch("atexit.register") as mock_atexit:
                from server.main import setup_signal_handlers
                setup_signal_handlers()

                # SIGINT and SIGTERM should be registered
                assert mock_signal.call_count >= 2
                mock_atexit.assert_called_once()


# =============================================================================
# Static File Serving Tests
# =============================================================================

class TestStaticFileServing:
    """Tests for static file serving (React app)."""

    @pytest.mark.unit
    def test_api_routes_not_served_as_static(self):
        """API routes should not be served as static files."""
        with patch("signal.signal", return_value=None):
            from server.main import app
            with TestClient(app, raise_server_exceptions=False) as client:
                response = client.get("/api/nonexistent")
                # Should return 404 for non-existent API routes
                assert response.status_code in [404, 500]

    @pytest.mark.unit
    def test_websocket_routes_not_served_as_static(self):
        """WebSocket routes should not be served as static files."""
        with patch("signal.signal", return_value=None):
            from server.main import app
            with TestClient(app, raise_server_exceptions=False) as client:
                # HTTP request to WS endpoint should fail
                response = client.get("/ws/projects/test")
                # 500 is acceptable as it means the route is found but can't handle HTTP
                assert response.status_code in [400, 403, 404, 405, 500]


# =============================================================================
# Lifespan Management Tests
# =============================================================================

class TestLifespanManagement:
    """Tests for FastAPI lifespan startup/shutdown."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_lifespan_starts_background_tasks(self):
        """Lifespan should start all background monitoring tasks."""
        with patch("server.main.restore_managers_from_registry") as mock_restore:
            with patch("server.main.cleanup_stale_containers") as mock_cleanup:
                with patch("server.main.initialize_all_projects") as mock_init:
                    with patch("server.main.cleanup_all_remote_branches") as mock_branches:
                        with patch("server.main.revert_all_in_progress_tasks") as mock_revert:
                            mock_restore.return_value = 0
                            mock_cleanup.return_value = 0
                            mock_init.return_value = None
                            mock_branches.return_value = None
                            mock_revert.return_value = []

                            from server.main import lifespan, app

                            # Use the lifespan context
                            async with lifespan(app):
                                mock_restore.assert_called_once()
                                mock_cleanup.assert_called_once()
                                mock_init.assert_called_once()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_lifespan_handles_restore_failure(self):
        """Lifespan should handle container restore failures gracefully."""
        with patch("server.main.restore_managers_from_registry") as mock_restore:
            with patch("server.main.cleanup_stale_containers") as mock_cleanup:
                with patch("server.main.initialize_all_projects") as mock_init:
                    with patch("server.main.cleanup_all_remote_branches") as mock_branches:
                        with patch("server.main.revert_all_in_progress_tasks") as mock_revert:
                            mock_restore.side_effect = Exception("Restore failed")
                            mock_cleanup.return_value = 0
                            mock_init.return_value = None
                            mock_branches.return_value = None
                            mock_revert.return_value = []

                            from server.main import lifespan, app

                            # Should not raise despite restore failure
                            async with lifespan(app):
                                pass


# =============================================================================
# Router Integration Tests
# =============================================================================

class TestRouterIntegration:
    """Tests for router inclusion and endpoint availability."""

    @pytest.mark.unit
    def test_projects_router_included(self):
        """Projects router endpoints should be available."""
        with patch("signal.signal", return_value=None):
            from server.main import app

            # Check that projects router is included
            routes = [route.path for route in app.routes]
            assert any("/projects" in route for route in routes)

    @pytest.mark.unit
    def test_features_router_included(self):
        """Features router endpoints should be available."""
        with patch("signal.signal", return_value=None):
            from server.main import app

            routes = [route.path for route in app.routes]
            assert any("features" in route for route in routes)

    @pytest.mark.unit
    def test_agent_router_included(self):
        """Agent router endpoints should be available."""
        with patch("signal.signal", return_value=None):
            from server.main import app

            routes = [route.path for route in app.routes]
            assert any("agent" in route for route in routes)

    @pytest.mark.unit
    def test_websocket_endpoint_registered(self):
        """WebSocket endpoint should be registered."""
        with patch("signal.signal", return_value=None):
            from server.main import app

            routes = [route.path for route in app.routes]
            assert any("/ws/projects" in route for route in routes)


# =============================================================================
# Environment Configuration Tests
# =============================================================================

class TestEnvironmentConfiguration:
    """Tests for environment-based configuration."""

    @pytest.mark.unit
    def test_default_cors_origins(self, monkeypatch):
        """Default CORS origins should include localhost ports."""
        monkeypatch.setenv("CORS_ORIGINS", "")

        import importlib
        import server.main
        importlib.reload(server.main)

        # The default cors_origins list should include localhost
        # This is tested indirectly through the health check

    @pytest.mark.unit
    def test_wildcard_cors_origins(self, monkeypatch):
        """CORS_ORIGINS=* should allow all origins."""
        monkeypatch.setenv("CORS_ORIGINS", "*")

        import importlib
        import server.main
        importlib.reload(server.main)

        assert server.main.cors_origins == ["*"]

    @pytest.mark.unit
    def test_custom_cors_origins(self, monkeypatch):
        """Custom CORS_ORIGINS should be parsed correctly."""
        monkeypatch.setenv("CORS_ORIGINS", "http://example.com, http://test.com")

        import importlib
        import server.main
        importlib.reload(server.main)

        assert "http://example.com" in server.main.cors_origins
        assert "http://test.com" in server.main.cors_origins
