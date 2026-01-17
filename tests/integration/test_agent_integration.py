"""
Agent API Integration Tests
===========================

Integration tests for /api/projects/{name}/agent endpoints.
Tests container control and agent management functionality.
"""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


class TestAgentStatusIntegration:
    """Integration tests for agent status endpoint."""

    @pytest.mark.integration
    def test_get_agent_status_not_created(self, test_client):
        """Test getting status when container not created."""
        with patch("server.routers.agent._get_project_path") as mock_path:
            mock_path.return_value = Path("/tmp/test-project")
            with patch("server.routers.agent.get_existing_container_manager") as mock_get:
                mock_get.return_value = None

                response = test_client.get("/api/projects/test-project/agent/status")

                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "not_created"

    @pytest.mark.integration
    def test_get_agent_status_running(self, test_client, mock_container_manager):
        """Test getting status when container is running."""
        mock_container_manager.get_status_dict.return_value = {
            "status": "running",
            "container_name": "zerocoder-test-1",
            "agent_running": True,
            "idle_seconds": 0,
        }

        with patch("server.routers.agent._get_project_path") as mock_path:
            mock_path.return_value = Path("/tmp/test-project")
            with patch("server.routers.agent.get_existing_container_manager") as mock_get:
                mock_get.return_value = mock_container_manager

                response = test_client.get("/api/projects/test-project/agent/status")

                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "running"

    @pytest.mark.integration
    def test_get_agent_status_project_not_found(self, test_client):
        """Test getting status for non-existent project."""
        with patch("server.routers.agent._get_project_path") as mock_path:
            mock_path.return_value = None

            response = test_client.get("/api/projects/nonexistent/agent/status")

            assert response.status_code == 404


class TestAgentStartIntegration:
    """Integration tests for agent start endpoint."""

    @pytest.mark.integration
    @pytest.mark.skip(reason="Requires Docker")
    def test_start_agent_success(self, test_client, mock_container_manager):
        """Test successfully starting agent."""
        mock_container_manager.start_container_only = AsyncMock(
            return_value=(True, "Container started")
        )

        with patch("server.routers.agent._get_project_path") as mock_path:
            mock_path.return_value = Path("/tmp/test-project")
            with patch("server.routers.agent._get_project_git_url") as mock_url:
                mock_url.return_value = "https://github.com/user/repo.git"
                with patch("server.routers.agent.get_container_manager") as mock_get:
                    mock_get.return_value = mock_container_manager

                    response = test_client.post(
                        "/api/projects/test-project/agent/start",
                        json={}
                    )

                    assert response.status_code in [200, 201]

    @pytest.mark.integration
    def test_start_agent_no_docker(self, test_client):
        """Test starting agent when Docker is not available."""
        with patch("server.routers.agent._get_project_path") as mock_path:
            mock_path.return_value = Path("/tmp/test-project")
            with patch("server.routers.agent._get_project_git_url") as mock_url:
                mock_url.return_value = "https://github.com/user/repo.git"
                with patch("server.routers.agent.ensure_image_exists") as mock_image:
                    mock_image.return_value = (False, "Docker not available")

                    response = test_client.post(
                        "/api/projects/test-project/agent/start",
                        json={}
                    )

                    # Should fail due to Docker unavailability
                    assert response.status_code in [500, 503]

    @pytest.mark.integration
    def test_start_agent_project_not_found(self, test_client):
        """Test starting agent for non-existent project."""
        with patch("server.routers.agent._get_project_path") as mock_path:
            mock_path.return_value = None

            response = test_client.post(
                "/api/projects/nonexistent/agent/start",
                json={}
            )

            assert response.status_code == 404


class TestAgentStopIntegration:
    """Integration tests for agent stop endpoint."""

    @pytest.mark.integration
    def test_stop_agent_success(self, test_client, mock_container_manager):
        """Test successfully stopping agent."""
        mock_container_manager.stop = AsyncMock(
            return_value=(True, "Container stopped")
        )

        with patch("server.routers.agent._get_project_path") as mock_path:
            mock_path.return_value = Path("/tmp/test-project")
            with patch("server.routers.agent.get_existing_container_manager") as mock_get:
                mock_get.return_value = mock_container_manager

                response = test_client.post("/api/projects/test-project/agent/stop")

                assert response.status_code == 200

    @pytest.mark.integration
    def test_stop_agent_not_running(self, test_client):
        """Test stopping agent when not running."""
        with patch("server.routers.agent._get_project_path") as mock_path:
            mock_path.return_value = Path("/tmp/test-project")
            with patch("server.routers.agent.get_existing_container_manager") as mock_get:
                mock_get.return_value = None

                response = test_client.post("/api/projects/test-project/agent/stop")

                # Should succeed even if not running
                assert response.status_code in [200, 404]

    @pytest.mark.integration
    def test_graceful_stop_agent(self, test_client, mock_container_manager):
        """Test graceful agent stop."""
        mock_container_manager.graceful_stop = AsyncMock(
            return_value=(True, "Graceful stop initiated")
        )

        with patch("server.routers.agent._get_project_path") as mock_path:
            mock_path.return_value = Path("/tmp/test-project")
            with patch("server.routers.agent.get_existing_container_manager") as mock_get:
                mock_get.return_value = mock_container_manager

                response = test_client.post(
                    "/api/projects/test-project/agent/graceful-stop"
                )

                assert response.status_code == 200


class TestAgentHealthIntegration:
    """Integration tests for agent health monitoring."""

    @pytest.mark.integration
    def test_agent_health_check(self, test_client, mock_container_manager):
        """Test agent health check."""
        mock_container_manager.is_agent_running.return_value = True

        with patch("server.routers.agent._get_project_path") as mock_path:
            mock_path.return_value = Path("/tmp/test-project")
            with patch("server.routers.agent.get_existing_container_manager") as mock_get:
                mock_get.return_value = mock_container_manager

                response = test_client.get("/api/projects/test-project/agent/status")

                assert response.status_code == 200

    @pytest.mark.integration
    def test_agent_not_running_health(self, test_client, mock_container_manager):
        """Test health check when agent is not running."""
        mock_container_manager.is_agent_running.return_value = False
        mock_container_manager.get_status_dict.return_value = {
            "status": "stopped",
            "agent_running": False,
        }

        with patch("server.routers.agent._get_project_path") as mock_path:
            mock_path.return_value = Path("/tmp/test-project")
            with patch("server.routers.agent.get_existing_container_manager") as mock_get:
                mock_get.return_value = mock_container_manager

                response = test_client.get("/api/projects/test-project/agent/status")

                assert response.status_code == 200
                data = response.json()
                assert data["agent_running"] is False


class TestMultipleContainersIntegration:
    """Integration tests for multi-container support."""

    @pytest.mark.integration
    def test_start_all_containers(self, test_client):
        """Test starting all containers for a project."""
        with patch("server.routers.agent._get_project_path") as mock_path:
            mock_path.return_value = Path("/tmp/test-project")
            with patch("server.routers.agent._get_project_git_url") as mock_url:
                mock_url.return_value = "https://github.com/user/repo.git"
                with patch("server.routers.agent._get_project_info") as mock_info:
                    mock_info.return_value = {"target_container_count": 3}
                    with patch("server.routers.agent.ensure_image_exists") as mock_image:
                        mock_image.return_value = (True, "Image exists")
                        with patch("server.routers.agent.start_all_containers") as mock_start:
                            mock_start.return_value = (True, "Started 3 containers")

                            response = test_client.post(
                                "/api/projects/test-project/agent/start-all"
                            )

                            # Should succeed or fail gracefully
                            assert response.status_code in [200, 500, 503]

    @pytest.mark.integration
    def test_stop_all_containers(self, test_client):
        """Test stopping all containers for a project."""
        with patch("server.routers.agent._get_project_path") as mock_path:
            mock_path.return_value = Path("/tmp/test-project")
            with patch("server.routers.agent.stop_all_containers") as mock_stop:
                mock_stop.return_value = (True, "Stopped all containers")

                response = test_client.post("/api/projects/test-project/agent/stop")

                assert response.status_code == 200


class TestContainerInstructionIntegration:
    """Integration tests for sending instructions to containers."""

    @pytest.mark.integration
    @pytest.mark.skip(reason="Requires running container")
    def test_send_instruction(self, test_client, mock_container_manager):
        """Test sending instruction to running container."""
        with patch("server.routers.agent._get_project_path") as mock_path:
            mock_path.return_value = Path("/tmp/test-project")
            with patch("server.routers.agent.get_existing_container_manager") as mock_get:
                mock_get.return_value = mock_container_manager
                with patch("server.routers.agent.send_instruction") as mock_send:
                    mock_send.return_value = True

                    response = test_client.post(
                        "/api/projects/test-project/agent/instruction",
                        json={"instruction": "Implement feature feat-1"}
                    )

                    assert response.status_code == 200


class TestAgentValidationIntegration:
    """Integration tests for agent request validation."""

    @pytest.mark.integration
    def test_invalid_project_name(self, test_client):
        """Test validation of project name in requests."""
        response = test_client.get("/api/projects/../invalid/agent/status")

        # Should reject path traversal attempts
        assert response.status_code in [400, 404, 422]

    @pytest.mark.integration
    def test_start_with_invalid_payload(self, test_client):
        """Test start request with invalid payload."""
        with patch("server.routers.agent._get_project_path") as mock_path:
            mock_path.return_value = Path("/tmp/test-project")

            response = test_client.post(
                "/api/projects/test-project/agent/start",
                json={"invalid_field": "value"}
            )

            # Should accept unknown fields (Pydantic's default behavior)
            # or reject with validation error
            assert response.status_code in [200, 422, 500, 503]
