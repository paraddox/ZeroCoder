"""
Tests for Remote Machine Manager
"""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


class TestRemoteMachineRegistry:
    """Test registry CRUD operations for remote machines."""

    def setup_method(self):
        """Set up test database."""
        import registry
        # Reset the engine to use in-memory database
        registry._engine = None
        registry._SessionLocal = None
        # Override to use in-memory SQLite
        import os
        os.environ["ZEROCODER_DATA_DIR"] = "/tmp/zerocoder_test"
        registry._engine = None
        registry._SessionLocal = None

    def test_add_remote_machine(self):
        import registry
        registry._engine = None
        registry._SessionLocal = None

        machine_id = registry.add_remote_machine(
            name="test-server",
            host="192.168.1.100",
            port=22,
            username="root",
            ssh_key_path="/tmp/test_key",
        )
        assert machine_id > 0

    def test_add_duplicate_machine_raises(self):
        import registry
        registry._engine = None
        registry._SessionLocal = None

        registry.add_remote_machine(name="dup-server", host="10.0.0.1")
        with pytest.raises(registry.RegistryError):
            registry.add_remote_machine(name="dup-server", host="10.0.0.2")

    def test_list_remote_machines(self):
        import registry
        registry._engine = None
        registry._SessionLocal = None

        registry.add_remote_machine(name="list-server-1", host="10.0.0.1")
        registry.add_remote_machine(name="list-server-2", host="10.0.0.2")

        machines = registry.list_remote_machines()
        names = [m["name"] for m in machines]
        assert "list-server-1" in names
        assert "list-server-2" in names

    def test_get_remote_machine(self):
        import registry
        registry._engine = None
        registry._SessionLocal = None

        mid = registry.add_remote_machine(name="get-server", host="10.0.0.3", port=2222, username="ubuntu")
        machine = registry.get_remote_machine(mid)
        assert machine is not None
        assert machine["name"] == "get-server"
        assert machine["host"] == "10.0.0.3"
        assert machine["port"] == 2222
        assert machine["username"] == "ubuntu"

    def test_remove_remote_machine(self):
        import registry
        registry._engine = None
        registry._SessionLocal = None

        mid = registry.add_remote_machine(name="rm-server", host="10.0.0.4")
        assert registry.remove_remote_machine(mid) is True
        assert registry.get_remote_machine(mid) is None

    def test_remove_nonexistent_machine(self):
        import registry
        registry._engine = None
        registry._SessionLocal = None

        assert registry.remove_remote_machine(99999) is False

    def test_update_machine_status(self):
        import registry
        registry._engine = None
        registry._SessionLocal = None

        mid = registry.add_remote_machine(name="status-server", host="10.0.0.5")
        registry.update_remote_machine_status(mid, "online")
        machine = registry.get_remote_machine(mid)
        assert machine["status"] == "online"
        assert machine["last_checked_at"] is not None


class TestRemoteAgentRegistry:
    """Test registry CRUD operations for remote agents."""

    def test_create_remote_agent(self):
        import registry
        registry._engine = None
        registry._SessionLocal = None

        # First register a project
        try:
            registry.register_project("test-proj", "git@github.com:test/repo.git")
        except registry.RegistryError:
            pass

        mid = registry.add_remote_machine(name="agent-server", host="10.0.0.10")
        agent_id = registry.create_remote_agent("test-proj", mid, agent_number=1)
        assert agent_id > 0

    def test_update_remote_agent(self):
        import registry
        registry._engine = None
        registry._SessionLocal = None

        try:
            registry.register_project("test-proj2", "git@github.com:test/repo2.git")
        except registry.RegistryError:
            pass

        mid = registry.add_remote_machine(name="agent-server-2", host="10.0.0.11")
        agent_id = registry.create_remote_agent("test-proj2", mid, agent_number=1)

        registry.update_remote_agent(agent_id, status="running", pid=12345)
        agent = registry.get_remote_agent(agent_id)
        assert agent["status"] == "running"
        assert agent["pid"] == 12345

    def test_get_agents_for_project(self):
        import registry
        registry._engine = None
        registry._SessionLocal = None

        try:
            registry.register_project("test-proj3", "git@github.com:test/repo3.git")
        except registry.RegistryError:
            pass

        mid = registry.add_remote_machine(name="agent-server-3", host="10.0.0.12")
        registry.create_remote_agent("test-proj3", mid, agent_number=1)
        registry.create_remote_agent("test-proj3", mid, agent_number=2)

        agents = registry.get_remote_agents_for_project("test-proj3")
        assert len(agents) >= 2

    def test_delete_remote_agent(self):
        import registry
        registry._engine = None
        registry._SessionLocal = None

        try:
            registry.register_project("test-proj4", "git@github.com:test/repo4.git")
        except registry.RegistryError:
            pass

        mid = registry.add_remote_machine(name="agent-server-4", host="10.0.0.13")
        agent_id = registry.create_remote_agent("test-proj4", mid, agent_number=1)
        assert registry.delete_remote_agent(agent_id) is True
        assert registry.get_remote_agent(agent_id) is None


class TestRemoteMachineManagerUnit:
    """Unit tests for RemoteMachineManager (mocked SSH)."""

    def test_manager_init(self):
        from server.services.remote_machine_manager import RemoteMachineManager

        manager = RemoteMachineManager(
            project_name="test",
            machine_id=1,
            git_url="git@github.com:test/repo.git",
            agent_number=1,
            agent_id=1,
        )
        assert manager.project_name == "test"
        assert manager.status == "created"
        assert manager.agent_number == 1

    def test_manager_callbacks(self):
        from server.services.remote_machine_manager import RemoteMachineManager

        manager = RemoteMachineManager(
            project_name="test",
            machine_id=1,
            git_url="git@github.com:test/repo.git",
            agent_number=1,
            agent_id=1,
        )

        cb = AsyncMock()
        manager.add_output_callback(cb)
        assert cb in manager._output_callbacks

        manager.remove_output_callback(cb)
        assert cb not in manager._output_callbacks

    def test_global_registry(self):
        from server.services.remote_machine_manager import (
            _remote_managers,
            get_all_remote_managers,
        )

        # Clean state
        _remote_managers.clear()

        assert get_all_remote_managers("nonexistent") == []

    def test_build_env_vars(self):
        from server.services.remote_machine_manager import RemoteMachineManager
        import os

        manager = RemoteMachineManager(
            project_name="myproject",
            machine_id=1,
            git_url="git@github.com:test/repo.git",
            agent_number=2,
            agent_id=5,
        )

        os.environ["ANTHROPIC_API_KEY"] = "test-key"
        env = manager._build_env_vars()
        assert env["PROJECT_NAME"] == "myproject"
        assert env["CONTAINER_NUMBER"] == "2"
        assert env["ANTHROPIC_API_KEY"] == "test-key"
        del os.environ["ANTHROPIC_API_KEY"]


class TestPydanticSchemas:
    """Test Pydantic schemas for remote machines."""

    def test_remote_machine_create(self):
        from server.schemas import RemoteMachineCreate

        schema = RemoteMachineCreate(
            name="test",
            host="192.168.1.1",
            port=22,
            username="root",
        )
        assert schema.name == "test"
        assert schema.port == 22

    def test_remote_machine_create_defaults(self):
        from server.schemas import RemoteMachineCreate

        schema = RemoteMachineCreate(name="test", host="10.0.0.1")
        assert schema.port == 22
        assert schema.username == "root"
        assert schema.ssh_key_path is None

    def test_remote_agent_start_request(self):
        from server.schemas import RemoteAgentStartRequest

        schema = RemoteAgentStartRequest(machine_id=5)
        assert schema.machine_id == 5

    def test_remote_agent_status_response(self):
        from server.schemas import RemoteAgentStatusResponse

        schema = RemoteAgentStatusResponse(
            id=1,
            project_name="proj",
            machine_id=2,
            machine_name="server-1",
            agent_number=1,
            status="running",
            current_feature=None,
            pid=12345,
            graceful_stop_requested=False,
            restarting=False,
            last_activity_at=None,
        )
        assert schema.status == "running"
        assert schema.pid == 12345
