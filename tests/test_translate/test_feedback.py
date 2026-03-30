"""Tests for FeedbackProvider abstraction and implementations."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from aat.storage.models import (
    Segment,
    SegmentState,
    StructuredFeedback,
    FeedbackCategory,
    TranslationSegment,
    UncertaintyItem,
)
from aat.translate.feedback import (
    AutoSkipFeedbackProvider,
    CheckpointPollingFeedbackProvider,
    FeedbackProvider,
    FeedbackResponse,
    InteractiveCLIFeedbackProvider,
)


def _make_segment(**overrides) -> TranslationSegment:
    """Create a minimal TranslationSegment for testing."""
    defaults = {
        "segment": Segment(sid="s1", pid_list=["p1"], source_text="Test text."),
        "state": SegmentState.USER_FEEDBACK_WAIT,
        "translation": "测试文本。",
    }
    defaults.update(overrides)
    return TranslationSegment(**defaults)


class TestFeedbackResponse:
    """Test FeedbackResponse dataclass."""

    def test_feedback_response_defaults(self) -> None:
        """FeedbackResponse with only action should have empty defaults."""
        resp = FeedbackResponse(action="skip")
        assert resp.action == "skip"
        assert resp.comments == []
        assert resp.answers == {}
        assert resp.structured_feedback == []

    def test_feedback_response_with_data(self) -> None:
        """FeedbackResponse with all fields populated."""
        fb = StructuredFeedback(category=FeedbackCategory.OMISSION, detail="missing")
        resp = FeedbackResponse(
            action="revise",
            comments=["fix this"],
            answers={"Q1": "A1"},
            structured_feedback=[fb],
        )
        assert resp.action == "revise"
        assert resp.comments == ["fix this"]
        assert resp.answers == {"Q1": "A1"}
        assert len(resp.structured_feedback) == 1


class TestAutoSkipFeedbackProvider:
    """Test AutoSkipFeedbackProvider."""

    def test_auto_skip_returns_skip(self) -> None:
        """get_feedback should always return action='skip'."""
        provider = AutoSkipFeedbackProvider()
        seg = _make_segment()
        resp = provider.get_feedback(seg)
        assert resp.action == "skip"

    def test_auto_skip_has_no_pending_empty_segment(self) -> None:
        """has_pending_feedback should return False for clean segment."""
        provider = AutoSkipFeedbackProvider()
        seg = _make_segment()
        assert provider.has_pending_feedback(seg) is False

    def test_auto_skip_has_pending_with_comments(self) -> None:
        """has_pending_feedback should return True when user_comments exist."""
        provider = AutoSkipFeedbackProvider()
        seg = _make_segment(user_comments=[{"text": "fix", "timestamp": "now"}])
        assert provider.has_pending_feedback(seg) is True


class TestInteractiveCLIFeedbackProvider:
    """Test InteractiveCLIFeedbackProvider."""

    def test_interactive_cli_approve(self) -> None:
        """Input 'a' should return action='approve'."""
        provider = InteractiveCLIFeedbackProvider()
        seg = _make_segment()
        with patch("click.prompt", return_value="a"):
            resp = provider.get_feedback(seg)
        assert resp.action == "approve"

    def test_interactive_cli_comment(self) -> None:
        """Input 'c' then comment text should return action='revise' with comment."""
        provider = InteractiveCLIFeedbackProvider()
        seg = _make_segment()
        with patch("click.prompt", side_effect=["c", "Please fix the tone"]):
            resp = provider.get_feedback(seg)
        assert resp.action == "revise"
        assert "Please fix the tone" in resp.comments

    def test_interactive_cli_skip(self) -> None:
        """Input 's' should return action='skip'."""
        provider = InteractiveCLIFeedbackProvider()
        seg = _make_segment()
        with patch("click.prompt", return_value="s"):
            resp = provider.get_feedback(seg)
        assert resp.action == "skip"


class TestFeedbackEdgeCases:
    """Edge-case tests for feedback types."""

    def test_feedback_response_invalid_action(self) -> None:
        """Invalid action doesn't crash -- it's just a data container."""
        resp = FeedbackResponse(action="invalid")
        assert resp.action == "invalid"

    def test_checkpoint_polling_timeout_zero_returns_immediately(self, tmp_path: Path) -> None:
        """With timeout=0, get_feedback should return in <100ms."""
        import time
        from aat.storage.checkpoints import CheckpointManager
        from tests.test_ui.test_project_loader import _create_test_checkpoint

        project_dir = _create_test_checkpoint(tmp_path, [
            {"sid": "s1", "translation": "test", "user_comments": []},
        ])
        cm = CheckpointManager(project_dir)
        provider = CheckpointPollingFeedbackProvider(cm, timeout=0)
        seg = _make_segment()

        start = time.monotonic()
        resp = provider.get_feedback(seg)
        elapsed = time.monotonic() - start

        assert resp.action == "skip"
        assert elapsed < 0.1


class TestFullFeedbackLoopE2E:
    """End-to-end integration test for the full feedback loop."""

    def test_full_feedback_loop_e2e(self) -> None:
        """Pipeline with revise-then-approve provider processes segment correctly."""
        from aat.storage.models import DocumentModel, Segment, SegmentState, TranslationProject, TranslationSegment
        from aat.translate.pipeline import PipelineConfig, TranslationPipeline

        call_count = 0

        class ReviseThenApproveProvider(FeedbackProvider):
            def get_feedback(self, segment):
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    fb = StructuredFeedback(
                        category=FeedbackCategory.OMISSION,
                        detail="Missing sentence",
                    )
                    return FeedbackResponse(
                        action="revise",
                        comments=["fix this"],
                        structured_feedback=[fb],
                    )
                return FeedbackResponse(action="approve")

        seg = Segment(sid="s1", pid_list=["p1"], source_text="Test text.")
        ts = TranslationSegment(
            segment=seg,
            state=SegmentState.USER_FEEDBACK_WAIT,
            translation="测试文本。",
        )

        project = TranslationProject.create(DocumentModel.create())
        project.segments = [ts]
        config = PipelineConfig(llm_provider="fake", enable_checkpoints=False)
        pipeline = TranslationPipeline(project, config=config, feedback_provider=ReviseThenApproveProvider())

        pipeline._process_segment(ts)

        assert ts.locked is True
        assert "fix this" in ts.user_comments
        assert len(ts.structured_feedback) >= 1


class TestCheckpointPollingFeedbackProvider:
    """Test CheckpointPollingFeedbackProvider."""

    def test_checkpoint_polling_no_feedback_returns_skip(self, tmp_path: Path) -> None:
        """No feedback in checkpoint and timeout=0 should return skip."""
        from aat.storage.checkpoints import CheckpointManager
        from tests.test_ui.test_project_loader import _create_test_checkpoint

        project_dir = _create_test_checkpoint(tmp_path, [
            {"sid": "s1", "translation": "test", "user_comments": []},
        ])
        cm = CheckpointManager(project_dir)
        provider = CheckpointPollingFeedbackProvider(cm, timeout=0)
        seg = _make_segment()
        resp = provider.get_feedback(seg)
        assert resp.action == "skip"

    def test_checkpoint_polling_with_feedback_returns_revise(self, tmp_path: Path) -> None:
        """Feedback present in checkpoint should return action='revise'."""
        from aat.storage.checkpoints import CheckpointManager
        from tests.test_ui.test_project_loader import _create_test_checkpoint

        project_dir = _create_test_checkpoint(tmp_path, [
            {
                "sid": "s1",
                "translation": "test",
                "user_comments": [{"text": "fix this", "timestamp": "now"}],
            },
        ])
        cm = CheckpointManager(project_dir)
        provider = CheckpointPollingFeedbackProvider(cm, timeout=0)
        seg = _make_segment(
            user_comments=[{"text": "fix this", "timestamp": "now"}],
        )
        resp = provider.get_feedback(seg)
        assert resp.action == "revise"
        assert len(resp.comments) > 0
