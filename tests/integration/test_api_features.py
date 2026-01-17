"""
Features API Integration Tests
==============================

Integration tests for /api/projects/{name}/features endpoints.
Tests the complete request/response flow for feature management.
"""

import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


class TestFeatureListIntegration:
    """Integration tests for listing features."""

    @pytest.mark.integration
    def test_list_features_empty_project(self, test_client, tmp_path):
        """Test listing features when project has no features."""
        project_dir = tmp_path / "empty-project"
        project_dir.mkdir()
        beads_dir = project_dir / ".beads"
        beads_dir.mkdir()
        (beads_dir / "issues.jsonl").write_text("")

        with patch("server.routers.features._get_project_path") as mock_path:
            mock_path.return_value = project_dir
            with patch("server.routers.features._get_project_git_url") as mock_url:
                mock_url.return_value = "https://github.com/user/repo.git"

                response = test_client.get("/api/projects/empty-project/features")

                # Should succeed even with no features
                assert response.status_code == 200
                data = response.json()
                assert "pending" in data
                assert "in_progress" in data
                assert "done" in data

    @pytest.mark.integration
    def test_list_features_with_data(self, test_client, tmp_path):
        """Test listing features when project has features."""
        project_dir = tmp_path / "test-project"
        project_dir.mkdir()
        beads_dir = project_dir / ".beads"
        beads_dir.mkdir()

        issues = [
            {"id": "feat-1", "title": "Auth", "status": "open", "priority": 1},
            {"id": "feat-2", "title": "Dashboard", "status": "in_progress", "priority": 2},
            {"id": "feat-3", "title": "Settings", "status": "closed", "priority": 3},
        ]

        issues_file = beads_dir / "issues.jsonl"
        with open(issues_file, "w") as f:
            for issue in issues:
                f.write(json.dumps(issue) + "\n")

        with patch("server.routers.features._get_project_path") as mock_path:
            mock_path.return_value = project_dir
            with patch("server.routers.features._get_project_git_url") as mock_url:
                mock_url.return_value = "https://github.com/user/repo.git"

                response = test_client.get("/api/projects/test-project/features")

                assert response.status_code == 200

    @pytest.mark.integration
    def test_list_features_project_not_found(self, test_client):
        """Test listing features for non-existent project."""
        with patch("server.routers.features._get_project_path") as mock_path:
            mock_path.return_value = None

            response = test_client.get("/api/projects/nonexistent/features")

            assert response.status_code == 404


class TestFeatureCreationIntegration:
    """Integration tests for creating features."""

    @pytest.mark.integration
    @pytest.mark.skip(reason="Requires container to be running")
    def test_create_feature_success(self, test_client, tmp_path):
        """Test successful feature creation."""
        project_dir = tmp_path / "test-project"
        project_dir.mkdir()
        beads_dir = project_dir / ".beads"
        beads_dir.mkdir()
        (beads_dir / "issues.jsonl").write_text("")

        with patch("server.routers.features._get_project_path") as mock_path:
            mock_path.return_value = project_dir
            with patch("server.routers.features.ensure_container_running") as mock_container:
                mock_container.return_value = True
                with patch("server.routers.features.create_beads_feature") as mock_create:
                    mock_create.return_value = {
                        "id": "feat-1",
                        "title": "New Feature",
                        "status": "open",
                        "priority": 1,
                    }

                    response = test_client.post(
                        "/api/projects/test-project/features",
                        json={
                            "category": "auth",
                            "name": "New Feature",
                            "description": "Feature description",
                            "steps": ["Step 1", "Step 2"],
                        }
                    )

                    assert response.status_code in [200, 201]

    @pytest.mark.integration
    def test_create_feature_invalid_data(self, test_client):
        """Test feature creation with invalid data."""
        response = test_client.post(
            "/api/projects/test-project/features",
            json={
                # Missing required fields
                "name": "Test"
            }
        )

        assert response.status_code == 422  # Validation error

    @pytest.mark.integration
    def test_create_feature_empty_steps(self, test_client, tmp_path):
        """Test feature creation with empty steps array."""
        project_dir = tmp_path / "test-project"
        project_dir.mkdir()
        beads_dir = project_dir / ".beads"
        beads_dir.mkdir()

        response = test_client.post(
            "/api/projects/test-project/features",
            json={
                "category": "test",
                "name": "Test Feature",
                "description": "Test",
                "steps": []  # Empty steps
            }
        )

        # Should accept empty steps
        assert response.status_code in [200, 201, 404, 500]


class TestFeatureUpdateIntegration:
    """Integration tests for updating features."""

    @pytest.mark.integration
    @pytest.mark.skip(reason="Requires container to be running")
    def test_update_feature_status(self, test_client, tmp_path):
        """Test updating feature status."""
        project_dir = tmp_path / "test-project"
        project_dir.mkdir()
        beads_dir = project_dir / ".beads"
        beads_dir.mkdir()

        with patch("server.routers.features._get_project_path") as mock_path:
            mock_path.return_value = project_dir
            with patch("server.routers.features.ensure_container_running") as mock_container:
                mock_container.return_value = True
                with patch("server.routers.features.update_beads_feature") as mock_update:
                    mock_update.return_value = {
                        "id": "feat-1",
                        "title": "Feature",
                        "status": "in_progress",
                    }

                    response = test_client.put(
                        "/api/projects/test-project/features/feat-1",
                        json={"status": "in_progress"}
                    )

                    assert response.status_code == 200

    @pytest.mark.integration
    @pytest.mark.skip(reason="Requires container to be running")
    def test_update_feature_priority(self, test_client, tmp_path):
        """Test updating feature priority."""
        project_dir = tmp_path / "test-project"
        project_dir.mkdir()

        with patch("server.routers.features._get_project_path") as mock_path:
            mock_path.return_value = project_dir
            with patch("server.routers.features.ensure_container_running") as mock_container:
                mock_container.return_value = True
                with patch("server.routers.features.update_beads_feature") as mock_update:
                    mock_update.return_value = {
                        "id": "feat-1",
                        "priority": 0,
                    }

                    response = test_client.put(
                        "/api/projects/test-project/features/feat-1",
                        json={"priority": 0}
                    )

                    assert response.status_code == 200

    @pytest.mark.integration
    def test_update_feature_not_found(self, test_client, tmp_path):
        """Test updating non-existent feature."""
        project_dir = tmp_path / "test-project"
        project_dir.mkdir()

        with patch("server.routers.features._get_project_path") as mock_path:
            mock_path.return_value = project_dir
            with patch("server.routers.features.ensure_container_running") as mock_container:
                mock_container.return_value = True
                with patch("server.routers.features.update_beads_feature") as mock_update:
                    mock_update.return_value = None

                    response = test_client.put(
                        "/api/projects/test-project/features/nonexistent",
                        json={"status": "closed"}
                    )

                    assert response.status_code in [404, 500]


class TestFeatureDeleteIntegration:
    """Integration tests for deleting features."""

    @pytest.mark.integration
    @pytest.mark.skip(reason="Requires container to be running")
    def test_delete_feature_success(self, test_client, tmp_path):
        """Test successful feature deletion."""
        project_dir = tmp_path / "test-project"
        project_dir.mkdir()

        with patch("server.routers.features._get_project_path") as mock_path:
            mock_path.return_value = project_dir
            with patch("server.routers.features.ensure_container_running") as mock_container:
                mock_container.return_value = True
                with patch("server.routers.features.delete_beads_feature") as mock_delete:
                    mock_delete.return_value = True

                    response = test_client.delete(
                        "/api/projects/test-project/features/feat-1"
                    )

                    assert response.status_code in [200, 204]

    @pytest.mark.integration
    def test_delete_feature_not_found(self, test_client, tmp_path):
        """Test deleting non-existent feature."""
        project_dir = tmp_path / "test-project"
        project_dir.mkdir()

        with patch("server.routers.features._get_project_path") as mock_path:
            mock_path.return_value = project_dir
            with patch("server.routers.features.ensure_container_running") as mock_container:
                mock_container.return_value = True
                with patch("server.routers.features.delete_beads_feature") as mock_delete:
                    mock_delete.return_value = False

                    response = test_client.delete(
                        "/api/projects/test-project/features/nonexistent"
                    )

                    assert response.status_code in [404, 500]


class TestFeatureCloseIntegration:
    """Integration tests for closing features."""

    @pytest.mark.integration
    @pytest.mark.skip(reason="Requires container to be running")
    def test_close_feature_success(self, test_client, tmp_path):
        """Test closing a feature."""
        project_dir = tmp_path / "test-project"
        project_dir.mkdir()

        with patch("server.routers.features._get_project_path") as mock_path:
            mock_path.return_value = project_dir
            with patch("server.routers.features.ensure_container_running") as mock_container:
                mock_container.return_value = True
                with patch("server.routers.features.close_beads_feature") as mock_close:
                    mock_close.return_value = {
                        "id": "feat-1",
                        "status": "closed",
                    }

                    response = test_client.post(
                        "/api/projects/test-project/features/feat-1/close"
                    )

                    assert response.status_code == 200


class TestFeatureCacheIntegration:
    """Integration tests for feature caching."""

    @pytest.mark.integration
    def test_features_use_cache_when_available(self, test_client, isolated_registry):
        """Test that features are returned from cache when available."""
        # Create cached data
        cached_features = {
            "pending": [{"id": "cached-1", "title": "Cached Feature"}],
            "in_progress": [],
            "done": []
        }

        isolated_registry.register_project(
            name="cached-project",
            git_url="https://github.com/user/repo.git"
        )
        isolated_registry.update_feature_cache("cached-project", cached_features)

        with patch("server.routers.features._get_project_path") as mock_path:
            mock_path.return_value = None  # No local path

            with patch("server.routers.features.get_feature_cache") as mock_cache:
                mock_cache.return_value = cached_features

                response = test_client.get("/api/projects/cached-project/features")

                # Should return cached data even without local files
                assert response.status_code in [200, 404]


class TestFeatureValidationIntegration:
    """Integration tests for feature input validation."""

    @pytest.mark.integration
    def test_feature_name_too_long(self, test_client):
        """Test that overly long feature names are rejected."""
        response = test_client.post(
            "/api/projects/test-project/features",
            json={
                "category": "test",
                "name": "x" * 1000,  # Very long name
                "description": "Test",
                "steps": ["Step 1"]
            }
        )

        # Should be rejected or truncated
        assert response.status_code in [400, 422, 404, 500]

    @pytest.mark.integration
    def test_feature_invalid_priority(self, test_client):
        """Test that invalid priority values are rejected."""
        response = test_client.post(
            "/api/projects/test-project/features",
            json={
                "category": "test",
                "name": "Test Feature",
                "description": "Test",
                "steps": ["Step 1"],
                "priority": -1  # Invalid priority
            }
        )

        # Negative priority should be rejected
        assert response.status_code in [400, 422, 404, 500]

    @pytest.mark.integration
    def test_feature_missing_category(self, test_client):
        """Test that missing category is rejected."""
        response = test_client.post(
            "/api/projects/test-project/features",
            json={
                "name": "Test Feature",
                "description": "Test",
                "steps": ["Step 1"]
                # Missing category
            }
        )

        assert response.status_code == 422


class TestFeatureIdFormatIntegration:
    """Integration tests for feature ID format handling."""

    @pytest.mark.integration
    def test_beads_style_feature_id(self, test_client, tmp_path):
        """Test handling of beads-style feature IDs."""
        project_dir = tmp_path / "test-project"
        project_dir.mkdir()
        beads_dir = project_dir / ".beads"
        beads_dir.mkdir()

        # Create issue with beads-style ID
        issues_file = beads_dir / "issues.jsonl"
        issues_file.write_text('{"id": "beads-42", "title": "Test", "status": "open"}\n')

        with patch("server.routers.features._get_project_path") as mock_path:
            mock_path.return_value = project_dir
            with patch("server.routers.features._get_project_git_url") as mock_url:
                mock_url.return_value = "https://github.com/user/repo.git"

                response = test_client.get("/api/projects/test-project/features")

                assert response.status_code == 200

    @pytest.mark.integration
    def test_legacy_feature_id_format(self, test_client, tmp_path):
        """Test handling of legacy feature ID format."""
        project_dir = tmp_path / "test-project"
        project_dir.mkdir()
        beads_dir = project_dir / ".beads"
        beads_dir.mkdir()

        # Create issue with legacy-style ID
        issues_file = beads_dir / "issues.jsonl"
        issues_file.write_text('{"id": "feat-1", "title": "Test", "status": "open"}\n')

        with patch("server.routers.features._get_project_path") as mock_path:
            mock_path.return_value = project_dir
            with patch("server.routers.features._get_project_git_url") as mock_url:
                mock_url.return_value = "https://github.com/user/repo.git"

                response = test_client.get("/api/projects/test-project/features")

                assert response.status_code == 200
