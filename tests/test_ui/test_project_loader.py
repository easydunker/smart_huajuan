"""Tests for ProjectLoader and checkpoint write-back methods."""

import json
from datetime import datetime
from pathlib import Path

import pytest

from aat.storage.checkpoints import Checkpoint, CheckpointManager


def _create_test_checkpoint(tmp_path: Path, segments_data: list[dict]) -> Path:
    """Create a test checkpoint file with given segment data.

    Args:
        tmp_path: Temporary directory for checkpoint storage.
        segments_data: List of dicts, each with keys like sid, source_text,
            translation, state, locked, uncertainties, etc.

    Returns:
        The tmp_path directory (project root).
    """
    segment_states = {}
    for seg in segments_data:
        sid = seg["sid"]
        segment_states[sid] = {
            "segment": {
                "sid": sid,
                "pid_list": [f"p_{sid}"],
                "source_text": seg.get("source_text", f"Source for {sid}"),
                "context_before": None,
                "context_after": None,
                "chapter_id": seg.get("chapter_id"),
                "metadata": {
                    "chapter_id": seg.get("chapter_id", "ch1"),
                },
            },
            "state": seg.get("state", "draft_translate"),
            "translation": seg.get("translation", f"Translation for {sid}"),
            "uncertainties": seg.get("uncertainties", []),
            "validator_results": seg.get("validator_results", []),
            "critic_issues": seg.get("critic_issues", []),
            "user_comments": seg.get("user_comments", []),
            "translation_notes": [],
            "locked": seg.get("locked", False),
        }

    checkpoint_data = {
        "project_id": "test-project",
        "timestamp": datetime.now().isoformat(),
        "segment_states": segment_states,
        "metadata": {
            "title": "Test Document",
            "total_segments": len(segments_data),
            "completed_segments": sum(1 for s in segments_data if s.get("locked")),
        },
    }

    checkpoints_dir = tmp_path / "checkpoints"
    checkpoints_dir.mkdir(parents=True, exist_ok=True)
    ts = checkpoint_data["timestamp"].replace(":", "-").replace(".", "-")
    filepath = checkpoints_dir / f"checkpoint_{ts}.json"
    filepath.write_text(json.dumps(checkpoint_data, ensure_ascii=False, indent=2))

    return tmp_path


THREE_SEGMENTS = [
    {"sid": "s1", "source_text": "First source.", "translation": "第一段翻译。", "chapter_id": "ch1"},
    {"sid": "s2", "source_text": "Second source.", "translation": "第二段翻译。", "chapter_id": "ch1"},
    {"sid": "s3", "source_text": "Third source.", "translation": "第三段翻译。", "chapter_id": "ch2"},
]


class TestProjectLoader:
    """Tests for ProjectLoader class."""

    def test_load_from_checkpoint(self, tmp_path: Path) -> None:
        """Loading a checkpoint with 3 segments should yield 3 segments."""
        from aat.ui.server import ProjectLoader

        project_dir = _create_test_checkpoint(tmp_path, THREE_SEGMENTS)
        loader = ProjectLoader(project_dir)

        segments = loader.get_segments()
        assert len(segments) == 3

    def test_get_segment_by_sid(self, tmp_path: Path) -> None:
        """get_segment should return correct source_text and translation."""
        from aat.ui.server import ProjectLoader

        project_dir = _create_test_checkpoint(tmp_path, THREE_SEGMENTS)
        loader = ProjectLoader(project_dir)

        seg = loader.get_segment("s1")
        assert seg is not None
        assert seg["source_text"] == "First source."
        assert seg["translation"] == "第一段翻译。"

    def test_get_segment_not_found(self, tmp_path: Path) -> None:
        """get_segment with nonexistent SID should return None."""
        from aat.ui.server import ProjectLoader

        project_dir = _create_test_checkpoint(tmp_path, THREE_SEGMENTS)
        loader = ProjectLoader(project_dir)

        assert loader.get_segment("nonexistent") is None

    def test_list_segments_pagination(self, tmp_path: Path) -> None:
        """Pagination should return correct page size and total count."""
        from aat.ui.server import ProjectLoader

        ten_segments = [
            {"sid": f"s{i}", "source_text": f"Source {i}.", "translation": f"翻译 {i}。"}
            for i in range(10)
        ]
        project_dir = _create_test_checkpoint(tmp_path, ten_segments)
        loader = ProjectLoader(project_dir)

        page, total = loader.list_segments(page=1, per_page=5)
        assert len(page) == 5
        assert total == 10

        page2, total2 = loader.list_segments(page=2, per_page=5)
        assert len(page2) == 5
        assert total2 == 10

    def test_get_stats(self, tmp_path: Path) -> None:
        """Stats should reflect correct locked/unlocked/uncertain counts."""
        from aat.ui.server import ProjectLoader

        segments = [
            {"sid": "s1", "locked": True, "state": "lock_segment"},
            {"sid": "s2", "locked": True, "state": "lock_segment"},
            {
                "sid": "s3",
                "locked": False,
                "uncertainties": [
                    {"type": "TERM", "span": "x", "question": "What is x?", "options": ["a", "b"]}
                ],
            },
        ]
        project_dir = _create_test_checkpoint(tmp_path, segments)
        loader = ProjectLoader(project_dir)

        stats = loader.get_stats()
        assert stats["total"] == 3
        assert stats["locked"] == 2
        assert stats["unlocked"] == 1
        assert stats["uncertain"] == 1
        assert stats["project_id"] == "test-project"

    def test_list_segments_filter_locked(self, tmp_path: Path) -> None:
        """Filtering by 'locked' should return only locked segments."""
        from aat.ui.server import ProjectLoader

        segments = [
            {"sid": "s1", "locked": True},
            {"sid": "s2", "locked": False},
            {"sid": "s3", "locked": True},
        ]
        project_dir = _create_test_checkpoint(tmp_path, segments)
        loader = ProjectLoader(project_dir)

        page, total = loader.list_segments(state_filter="locked")
        assert total == 2
        assert all(s["locked"] for s in page)

    def test_list_segments_filter_uncertain(self, tmp_path: Path) -> None:
        """Filtering by 'uncertain' should return only segments with uncertainties."""
        from aat.ui.server import ProjectLoader

        segments = [
            {"sid": "s1", "uncertainties": [{"type": "TERM", "span": "x", "question": "?", "options": []}]},
            {"sid": "s2", "uncertainties": []},
        ]
        project_dir = _create_test_checkpoint(tmp_path, segments)
        loader = ProjectLoader(project_dir)

        page, total = loader.list_segments(state_filter="uncertain")
        assert total == 1
        assert page[0]["sid"] == "s1"

    def test_empty_checkpoint_dir(self, tmp_path: Path) -> None:
        """ProjectLoader with no checkpoints should return empty segments."""
        from aat.ui.server import ProjectLoader

        (tmp_path / "checkpoints").mkdir()
        loader = ProjectLoader(tmp_path)

        assert loader.get_segments() == []
        stats = loader.get_stats()
        assert stats["total"] == 0


class TestCheckpointWriteBack:
    """Tests for checkpoint write-back methods on CheckpointManager."""

    def test_lock_segment(self, tmp_path: Path) -> None:
        """lock_segment should set locked=True and state=lock_segment."""
        project_dir = _create_test_checkpoint(tmp_path, [
            {"sid": "s1", "locked": False, "state": "draft_translate"},
        ])
        cm = CheckpointManager(project_dir)

        result = cm.lock_segment("s1")
        assert result is True

        reloaded = cm.load_latest_checkpoint()
        assert reloaded.segment_states["s1"]["locked"] is True
        assert reloaded.segment_states["s1"]["state"] == "lock_segment"

    def test_add_comment(self, tmp_path: Path) -> None:
        """add_comment should append a comment with timestamp."""
        project_dir = _create_test_checkpoint(tmp_path, [
            {"sid": "s1"},
        ])
        cm = CheckpointManager(project_dir)

        result = cm.add_comment("s1", "test comment")
        assert result is True

        reloaded = cm.load_latest_checkpoint()
        comments = reloaded.segment_states["s1"]["user_comments"]
        assert len(comments) == 1
        assert comments[0]["text"] == "test comment"
        assert "timestamp" in comments[0]

    def test_update_translation(self, tmp_path: Path) -> None:
        """update_translation should change the translation text."""
        project_dir = _create_test_checkpoint(tmp_path, [
            {"sid": "s1", "translation": "old text"},
        ])
        cm = CheckpointManager(project_dir)

        result = cm.update_translation("s1", "新翻译文本")
        assert result is True

        reloaded = cm.load_latest_checkpoint()
        assert reloaded.segment_states["s1"]["translation"] == "新翻译文本"

    def test_update_nonexistent_segment(self, tmp_path: Path) -> None:
        """update_segment with a bad SID should return False."""
        project_dir = _create_test_checkpoint(tmp_path, [
            {"sid": "s1"},
        ])
        cm = CheckpointManager(project_dir)

        result = cm.update_segment("bad_id", {"locked": True})
        assert result is False

    def test_add_comment_migrates_old_format(self, tmp_path: Path) -> None:
        """Old-format string comments should be migrated to dict format."""
        project_dir = _create_test_checkpoint(tmp_path, [
            {"sid": "s1", "user_comments": ["old comment"]},
        ])
        cm = CheckpointManager(project_dir)

        result = cm.add_comment("s1", "new comment")
        assert result is True

        reloaded = cm.load_latest_checkpoint()
        comments = reloaded.segment_states["s1"]["user_comments"]
        assert len(comments) == 2
        assert comments[0]["text"] == "old comment"
        assert comments[0]["timestamp"] == "unknown"
        assert comments[1]["text"] == "new comment"

    def test_update_segment_no_checkpoint(self, tmp_path: Path) -> None:
        """update_segment with no checkpoints should return False."""
        (tmp_path / "checkpoints").mkdir()
        cm = CheckpointManager(tmp_path)

        result = cm.update_segment("s1", {})
        assert result is False
