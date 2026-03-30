"""Tests for revision, structured feedback, and preferences UI endpoints."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from aat.storage.checkpoints import CheckpointManager
from aat.ui.server import app, create_app

from tests.test_ui.test_project_loader import _create_test_checkpoint


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    """Create a test client with segments loaded."""
    segments = [
        {
            "sid": "s1",
            "source_text": "Introduction paragraph.",
            "translation": "介绍段落。",
            "locked": False,
            "state": "draft_translate",
            "chapter_id": "ch1",
        },
        {
            "sid": "s2",
            "source_text": "Methods paragraph.",
            "translation": "方法段落。",
            "locked": False,
            "state": "draft_translate",
            "chapter_id": "ch1",
        },
    ]
    project_dir = _create_test_checkpoint(tmp_path, segments)
    create_app(project_dir)
    return TestClient(app)


class TestStructuredFeedbackEndpoint:
    """Tests for POST /segments/{sid}/structured-feedback."""

    def test_structured_feedback_endpoint_stores_feedback(self, client: TestClient, tmp_path: Path) -> None:
        """POSTing structured feedback should store it in checkpoint."""
        resp = client.post(
            "/segments/s1/structured-feedback",
            data={"category": "OMISSION", "detail": "Missing sentence"},
            follow_redirects=False,
        )
        assert resp.status_code == 303

        detail = client.get("/segments/s1")
        assert "Missing sentence" in detail.text

    def test_structured_feedback_with_optional_fields(self, client: TestClient) -> None:
        """Optional span and suggested_fix should be stored."""
        resp = client.post(
            "/segments/s1/structured-feedback",
            data={
                "category": "WRONG_TERMINOLOGY",
                "detail": "Wrong term",
                "span": "test span",
                "suggested_fix": "add it",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 303


class TestReviseEndpoint:
    """Tests for POST /segments/{sid}/revise."""

    def test_revise_endpoint_updates_translation(self, client: TestClient) -> None:
        """POSTing to /revise should update translation via LLM."""
        resp = client.post("/segments/s1/revise", follow_redirects=False)
        assert resp.status_code == 303

    def test_revise_endpoint_not_initialized(self) -> None:
        """Revise without initialization should return 503."""
        from aat.ui import server
        old_loader = server.loader
        old_cm = server.checkpoint_manager
        server.loader = None
        server.checkpoint_manager = None
        try:
            tc = TestClient(app)
            resp = tc.post("/segments/s1/revise", follow_redirects=False)
            assert resp.status_code == 503
        finally:
            server.loader = old_loader
            server.checkpoint_manager = old_cm


class TestPreferencesEndpoints:
    """Tests for preferences endpoints."""

    def test_preferences_page_loads(self, client: TestClient) -> None:
        """GET /preferences should return 200."""
        resp = client.get("/preferences")
        assert resp.status_code == 200

    def test_save_preferences_style(self, client: TestClient) -> None:
        """POST /preferences should save style preferences."""
        resp = client.post(
            "/preferences",
            data={"formality": "formal", "tone": "academic"},
            follow_redirects=False,
        )
        assert resp.status_code == 303

    def test_add_term_override(self, client: TestClient) -> None:
        """POST /preferences/term should add a terminology override."""
        resp = client.post(
            "/preferences/term",
            data={"source": "entropy", "target": "熵"},
            follow_redirects=False,
        )
        assert resp.status_code == 303

    def test_delete_term_override(self, client: TestClient) -> None:
        """POST /preferences/term/delete should remove a terminology override."""
        client.post(
            "/preferences/term",
            data={"source": "entropy", "target": "熵"},
            follow_redirects=False,
        )
        resp = client.post(
            "/preferences/term/delete",
            data={"source": "entropy"},
            follow_redirects=False,
        )
        assert resp.status_code == 303


class TestRevisionEdgeCases:
    """Edge-case tests for revision endpoints."""

    def test_revise_segment_not_found(self, client: TestClient) -> None:
        """POST /segments/nonexistent/revise should return 404."""
        resp = client.post("/segments/nonexistent/revise", follow_redirects=False)
        assert resp.status_code == 404

    def test_structured_feedback_missing_required_field(self, client: TestClient) -> None:
        """POST without 'detail' should return 422."""
        resp = client.post(
            "/segments/s1/structured-feedback",
            data={"category": "OMISSION"},
            follow_redirects=False,
        )
        assert resp.status_code == 422


class TestNeedsRevisionFilter:
    """Tests for needs_revision filter."""

    def test_needs_revision_filter(self, tmp_path: Path) -> None:
        """Segments with revision_requested should show in needs_revision filter."""
        segments = [
            {"sid": "s1", "source_text": "First.", "translation": "第一。"},
            {"sid": "s2", "source_text": "Second.", "translation": "第二。"},
        ]
        project_dir = _create_test_checkpoint(tmp_path, segments)
        cm = CheckpointManager(project_dir)
        cm.request_revision("s1")

        create_app(project_dir)
        tc = TestClient(app)
        resp = tc.get("/segments?filter=needs_revision")
        assert resp.status_code == 200
        assert "s1" in resp.text
