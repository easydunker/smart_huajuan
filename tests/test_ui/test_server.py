"""Tests for FastAPI server routes."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from aat.storage.checkpoints import CheckpointManager
from aat.ui.server import app, create_app

from tests.test_ui.test_project_loader import _create_test_checkpoint


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    """Create a test client with 3 segments loaded."""
    segments = [
        {
            "sid": "s1",
            "source_text": "Introduction paragraph.",
            "translation": "介绍段落。",
            "locked": True,
            "state": "lock_segment",
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
        {
            "sid": "s3",
            "source_text": "Results paragraph with uncertainty.",
            "translation": "结果段落。",
            "locked": False,
            "state": "draft_translate",
            "chapter_id": "ch2",
            "uncertainties": [
                {"type": "TERM", "span": "significance", "question": "Which meaning?", "options": ["统计显著性", "重要性"]},
            ],
        },
    ]
    project_dir = _create_test_checkpoint(tmp_path, segments)
    create_app(project_dir)
    return TestClient(app)


class TestGetRoutes:
    """Tests for GET routes."""

    def test_root_redirects_to_segments(self, client: TestClient) -> None:
        """GET / should redirect to /segments."""
        resp = client.get("/", follow_redirects=False)
        assert resp.status_code == 307
        assert "/segments" in resp.headers["location"]

    def test_segments_page_returns_html(self, client: TestClient) -> None:
        """GET /segments should return 200 with segment data in HTML."""
        resp = client.get("/segments")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        assert "Introduction" in resp.text or "s1" in resp.text

    def test_segments_filter_locked(self, client: TestClient) -> None:
        """GET /segments?filter=locked should show only locked segments."""
        resp = client.get("/segments?filter=locked")
        assert resp.status_code == 200
        assert "Introduction" in resp.text or "s1" in resp.text

    def test_api_status_returns_json(self, client: TestClient) -> None:
        """GET /api/status should return JSON with stat keys."""
        resp = client.get("/api/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 3
        assert data["locked"] == 1
        assert data["unlocked"] == 2
        assert "project_id" in data


class TestSegmentDetail:
    """Tests for segment detail view and POST actions."""

    def test_segment_detail_returns_html(self, client: TestClient) -> None:
        """GET /segments/s1 should return 200 with source and translation."""
        resp = client.get("/segments/s1")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        assert "Introduction paragraph." in resp.text
        assert "介绍段落。" in resp.text

    def test_segment_detail_not_found(self, client: TestClient) -> None:
        """GET /segments/nonexistent should return 404."""
        resp = client.get("/segments/nonexistent")
        assert resp.status_code == 404

    def test_approve_locks_segment(self, client: TestClient, tmp_path: Path) -> None:
        """POST /segments/s2/approve should lock the segment and redirect."""
        resp = client.post("/segments/s2/approve", follow_redirects=False)
        assert resp.status_code in (302, 303, 307)

        status_resp = client.get("/api/status")
        data = status_resp.json()
        assert data["locked"] == 2  # s1 was already locked, now s2 too

    def test_add_comment(self, client: TestClient, tmp_path: Path) -> None:
        """POST /segments/s1/comment should store comment and redirect."""
        resp = client.post(
            "/segments/s1/comment",
            data={"comment": "Looks good!"},
            follow_redirects=False,
        )
        assert resp.status_code in (302, 303, 307)

        detail = client.get("/segments/s1")
        assert "Looks good!" in detail.text

    def test_edit_translation(self, client: TestClient, tmp_path: Path) -> None:
        """POST /segments/s2/edit should update translation and redirect."""
        resp = client.post(
            "/segments/s2/edit",
            data={"translation": "新的方法段落翻译。"},
            follow_redirects=False,
        )
        assert resp.status_code in (302, 303, 307)

        detail = client.get("/segments/s2")
        assert "新的方法段落翻译。" in detail.text

    def test_approve_already_locked(self, client: TestClient) -> None:
        """POST /segments/s1/approve on already-locked segment should succeed."""
        resp = client.post("/segments/s1/approve", follow_redirects=False)
        assert resp.status_code in (302, 303, 307)

    def test_terminology_page_returns_html(self, client: TestClient) -> None:
        """GET /terminology should return 200 with HTML."""
        resp = client.get("/terminology")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        assert "Terminology" in resp.text

    def test_approve_nonexistent_segment_returns_error(self, client: TestClient) -> None:
        """POST /segments/nonexistent/approve should return error, not silent success."""
        resp = client.post("/segments/nonexistent/approve", follow_redirects=False)
        assert resp.status_code in (404, 500), (
            f"Expected 404 for nonexistent segment, got {resp.status_code}"
        )

    def test_edit_locked_segment_rejected(self, client: TestClient) -> None:
        """POST /segments/s1/edit on locked segment should be rejected."""
        resp = client.post(
            "/segments/s1/edit",
            data={"translation": "attempted edit"},
            follow_redirects=False,
        )
        assert resp.status_code in (409, 403), (
            f"Expected 409 for locked segment edit, got {resp.status_code}"
        )

    def test_segment_detail_shows_structured_feedback_section(self, client: TestClient) -> None:
        """GET /segments/s1 should contain 'Structured Feedback' section."""
        resp = client.get("/segments/s1")
        assert resp.status_code == 200
        assert "Structured Feedback" in resp.text

    def test_preferences_link_in_nav(self, client: TestClient) -> None:
        """GET /segments should contain a link to /preferences."""
        resp = client.get("/segments")
        assert resp.status_code == 200
        assert 'href="/preferences"' in resp.text

    def test_answer_uncertainty(self, client: TestClient) -> None:
        """POST /segments/s3/answer should clear uncertainty and redirect."""
        resp = client.post(
            "/segments/s3/answer",
            data={"question": "Which meaning?", "answer": "统计显著性", "custom_answer": ""},
            follow_redirects=False,
        )
        assert resp.status_code == 303

        detail = client.get("/segments/s3")
        assert "Which meaning?" not in detail.text or "统计显著性" in detail.text
