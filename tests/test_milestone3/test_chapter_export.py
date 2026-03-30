"""Unit tests for Chapter Export functionality."""

import json
import tempfile
from pathlib import Path

import pytest

from aat.export.chapter import SegmentCheckpoint, ChapterExporter, ChapterExportError


class TestSegmentCheckpoint:
    """Test SegmentCheckpoint dataclass."""

    def test_create_from_segment(self) -> None:
        """Test creating checkpoint from segment data."""
        checkpoint = SegmentCheckpoint.create_from_segment(
            sid="s1",
            source_text="This is the source text.",
            translation="This is the translation.",
            state="LOCKED",
            locked=True,
        )

        assert checkpoint.sid == "s1"
        assert checkpoint.translation == "This is the translation."
        assert checkpoint.state == "LOCKED"
        assert checkpoint.locked is True
        assert checkpoint.source_hash  # Should have a hash
        assert len(checkpoint.source_hash) == 64  # SHA256

    def test_is_approved(self) -> None:
        """Test approval check."""
        # Approved: locked with translation
        approved = SegmentCheckpoint.create_from_segment(
            sid="s1",
            source_text="Source",
            translation="Translation",
            state="LOCKED",
            locked=True,
        )
        assert approved.is_approved() is True

        # Not approved: unlocked
        unlocked = SegmentCheckpoint.create_from_segment(
            sid="s2",
            source_text="Source",
            translation="Translation",
            state="DRAFT",
            locked=False,
        )
        assert unlocked.is_approved() is False

        # Not approved: no translation
        no_translation = SegmentCheckpoint.create_from_segment(
            sid="s3",
            source_text="Source",
            translation=None,
            state="DRAFT",
            locked=True,
        )
        assert no_translation.is_approved() is False

    def test_to_dict_and_from_dict(self) -> None:
        """Test JSON serialization/deserialization."""
        original = SegmentCheckpoint.create_from_segment(
            sid="s1",
            source_text="Source",
            translation="Translation",
            state="LOCKED",
            locked=True,
        )

        data = original.to_dict()
        assert data["sid"] == "s1"
        assert data["translation"] == "Translation"
        assert data["locked"] is True

        restored = SegmentCheckpoint.from_dict(data)
        assert restored.sid == original.sid
        assert restored.translation == original.translation
        assert restored.locked == original.locked
        assert restored.source_hash == original.source_hash


class TestChapterExporter:
    """Test ChapterExporter functionality."""

    @pytest.fixture
    def temp_project_dir(self) -> Path:
        """Create a temporary project directory."""
        return Path(tempfile.mkdtemp())

    @pytest.fixture
    def exporter(self, temp_project_dir: Path) -> ChapterExporter:
        """Create a ChapterExporter instance."""
        return ChapterExporter(temp_project_dir)

    def test_load_segment_checkpoints_empty(self, exporter: ChapterExporter) -> None:
        """Test loading checkpoints when none exist."""
        checkpoints = exporter.load_segment_checkpoints()
        assert checkpoints == {}

    def test_load_segment_checkpoints(self, exporter: ChapterExporter) -> None:
        """Test loading existing checkpoints."""
        # Create checkpoint file
        checkpoint_file = exporter.checkpoints_dir / "checkpoint_test.json"
        checkpoint_file.parent.mkdir(parents=True, exist_ok=True)

        checkpoint_data = {
            "project_id": "test-project",
            "timestamp": "2024-01-01T00:00:00",
            "segment_states": {
                "s1": {
                    "sid": "s1",
                    "source_hash": "abc123",
                    "translation": "Translation 1",
                    "state": "LOCKED",
                    "locked": True,
                    "metadata": {"chapter_id": "ch1"},
                },
                "s2": {
                    "sid": "s2",
                    "source_hash": "def456",
                    "translation": "Translation 2",
                    "state": "DRAFT",
                    "locked": False,
                    "metadata": {"chapter_id": "ch1"},
                },
            },
            "metadata": {},
        }

        with open(checkpoint_file, "w", encoding="utf-8") as f:
            json.dump(checkpoint_data, f)

        checkpoints = exporter.load_segment_checkpoints()

        assert len(checkpoints) == 2
        assert "s1" in checkpoints
        assert "s2" in checkpoints
        assert checkpoints["s1"].locked is True
        assert checkpoints["s2"].locked is False

    def test_corrupted_checkpoint_handled(self, exporter: ChapterExporter) -> None:
        """Test that corrupted checkpoint files are handled gracefully."""
        # Create corrupted checkpoint file
        checkpoint_file = exporter.checkpoints_dir / "checkpoint_corrupted.json"
        checkpoint_file.parent.mkdir(parents=True, exist_ok=True)

        with open(checkpoint_file, "w", encoding="utf-8") as f:
            f.write("invalid json {{{")

        # Should not raise exception
        checkpoints = exporter.load_segment_checkpoints()
        assert checkpoints == {}

    def test_get_chapter_segments(self, exporter: ChapterExporter) -> None:
        """Test getting approved segments for a chapter."""
        # Create checkpoints
        checkpoint_file = exporter.checkpoints_dir / "checkpoint_test.json"
        checkpoint_file.parent.mkdir(parents=True, exist_ok=True)

        checkpoint_data = {
            "project_id": "test-project",
            "timestamp": "2024-01-01T00:00:00",
            "segment_states": {
                "s1": {
                    "sid": "s1",
                    "source_hash": "abc123",
                    "translation": "Translation 1",
                    "state": "LOCKED",
                    "locked": True,
                    "metadata": {"chapter_id": "ch1"},
                },
                "s2": {
                    "sid": "s2",
                    "source_hash": "def456",
                    "translation": "Translation 2",
                    "state": "DRAFT",
                    "locked": False,
                    "metadata": {"chapter_id": "ch1"},
                },
                "s3": {
                    "sid": "s3",
                    "source_hash": "ghi789",
                    "translation": "Translation 3",
                    "state": "LOCKED",
                    "locked": True,
                    "metadata": {"chapter_id": "ch2"},
                },
            },
            "metadata": {},
        }

        with open(checkpoint_file, "w", encoding="utf-8") as f:
            json.dump(checkpoint_data, f)

        checkpoints = exporter.load_segment_checkpoints()
        chapter1_segments = exporter.get_chapter_segments("ch1", checkpoints)

        # Only s1 should be returned (approved segment from ch1)
        assert len(chapter1_segments) == 1
        assert chapter1_segments[0].sid == "s1"
        assert chapter1_segments[0].is_approved() is True

    def test_export_chapter(self, exporter: ChapterExporter) -> None:
        """Test exporting a chapter."""
        # Create checkpoint file
        checkpoint_file = exporter.checkpoints_dir / "checkpoint_test.json"
        checkpoint_file.parent.mkdir(parents=True, exist_ok=True)

        checkpoint_data = {
            "project_id": "test-project",
            "timestamp": "2024-01-01T00:00:00",
            "segment_states": {
                "s1": {
                    "sid": "s1",
                    "source_hash": "abc123",
                    "translation": "Translation 1",
                    "state": "LOCKED",
                    "locked": True,
                    "metadata": {"chapter_id": "ch1"},
                },
                "s2": {
                    "sid": "s2",
                    "source_hash": "def456",
                    "translation": "Translation 2",
                    "state": "DRAFT",
                    "locked": False,
                    "metadata": {"chapter_id": "ch1"},
                },
            },
            "metadata": {},
        }

        with open(checkpoint_file, "w", encoding="utf-8") as f:
            json.dump(checkpoint_data, f)

        # Export without output path
        result = exporter.export_chapter("ch1")

        assert result["success"] is True
        assert len(result["exported_segments"]) == 1
        assert result["exported_segments"][0]["sid"] == "s1"
        assert len(result["warnings"]) > 0  # Should warn about unapproved segments

    def test_export_chapter_to_file(self, exporter: ChapterExporter, temp_project_dir: Path) -> None:
        """Test exporting a chapter to a file."""
        # Create checkpoint file
        checkpoint_file = exporter.checkpoints_dir / "checkpoint_test.json"
        checkpoint_file.parent.mkdir(parents=True, exist_ok=True)

        checkpoint_data = {
            "project_id": "test-project",
            "timestamp": "2024-01-01T00:00:00",
            "segment_states": {
                "s1": {
                    "sid": "s1",
                    "source_hash": "abc123",
                    "translation": "Translation 1",
                    "state": "LOCKED",
                    "locked": True,
                    "metadata": {"chapter_id": "ch1"},
                },
            },
            "metadata": {},
        }

        with open(checkpoint_file, "w", encoding="utf-8") as f:
            json.dump(checkpoint_data, f)

        output_path = temp_project_dir / "export" / "ch1.json"

        result = exporter.export_chapter("ch1", output_path)

        assert result["success"] is True
        assert result["output_path"] == str(output_path)
        assert output_path.exists()

        # Verify file contents
        with open(output_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert data["success"] is True
        assert len(data["exported_segments"]) == 1

    def test_list_chapters(self, exporter: ChapterExporter) -> None:
        """Test listing all chapters."""
        # Create checkpoint file
        checkpoint_file = exporter.checkpoints_dir / "checkpoint_test.json"
        checkpoint_file.parent.mkdir(parents=True, exist_ok=True)

        checkpoint_data = {
            "project_id": "test-project",
            "timestamp": "2024-01-01T00:00:00",
            "segment_states": {
                "s1": {
                    "sid": "s1",
                    "source_hash": "abc123",
                    "translation": "Translation 1",
                    "state": "LOCKED",
                    "locked": True,
                    "metadata": {"chapter_id": "ch1"},
                },
                "s2": {
                    "sid": "s2",
                    "source_hash": "def456",
                    "translation": "Translation 2",
                    "state": "DRAFT",
                    "locked": False,
                    "metadata": {"chapter_id": "ch1"},
                },
                "s3": {
                    "sid": "s3",
                    "source_hash": "ghi789",
                    "translation": "Translation 3",
                    "state": "LOCKED",
                    "locked": True,
                    "metadata": {"chapter_id": "ch2"},
                },
                "s4": {
                    "sid": "s4",
                    "source_hash": "jkl012",
                    "translation": "Translation 4",
                    "state": "LOCKED",
                    "locked": True,
                    "metadata": {"chapter_id": "ch2"},
                },
            },
            "metadata": {},
        }

        with open(checkpoint_file, "w", encoding="utf-8") as f:
            json.dump(checkpoint_data, f)

        chapters = exporter.list_chapters()

        assert len(chapters) == 2

        # Chapter 1: 2 total, 1 approved
        ch1 = next((c for c in chapters if c["chapter_id"] == "ch1"), None)
        assert ch1 is not None
        assert ch1["total_segments"] == 2
        assert ch1["approved_segments"] == 1
        assert ch1["complete"] is False

        # Chapter 2: 2 total, 2 approved
        ch2 = next((c for c in chapters if c["chapter_id"] == "ch2"), None)
        assert ch2 is not None
        assert ch2["total_segments"] == 2
        assert ch2["approved_segments"] == 2
        assert ch2["complete"] is True
