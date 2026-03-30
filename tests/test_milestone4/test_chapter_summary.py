"""Unit tests for Chapter Summary Generator."""

import tempfile
from pathlib import Path

import pytest

from aat.orchestrator.chapter_summary import (
    ChapterSummary,
    generate_chapter_summary,
    save_chapter_summary,
    load_chapter_summary,
    list_chapter_summaries,
)


class TestChapterSummary:
    "Test ChapterSummary dataclass."

    def test_creation(self) -> None:
        "Test creating a chapter summary."
        summary = ChapterSummary(
            project_id="test-project",
            chapter_id="ch1",
            summary="This is a chapter summary.",
            generated_at="2024-01-01T00:00:00",
        )

        assert summary.project_id == "test-project"
        assert summary.chapter_id == "ch1"
        assert summary.summary == "This is a chapter summary."
        assert len(summary.generated_at) > 0

    def test_to_to_dict_and_from_dict(self) -> None:
        "Test JSON serialization/deserialization."
        original = ChapterSummary(
            project_id="test-project",
            chapter_id="ch1",
            summary="Summary text",
            generated_at="2024-01-01T00:00:00",
            metadata={"segment_count": 10},
        )

        data = original.to_dict()
        assert data["project_id"] == "test-project"
        assert data["summary"] == "Summary text"

        restored = ChapterSummary.from_dict(data)
        assert restored.project_id == original.project_id
        assert restored.summary == original.summary
        assert restored.metadata == original.metadata

    def test_to_json_and_from_json(self) -> None:
        "Test JSON string serialization/deserialization."
        original = ChapterSummary(
            project_id="test-project",
            chapter_id="ch1",
            summary="Summary text",
            generated_at="2024-01-01T00:00:00",
        )

        json_str = original.to_json()
        assert isinstance(json_str, str)

        restored = ChapterSummary.from_json(json_str)
        assert restored.project_id == original.project_id
        assert restored.summary == original.summary


class TestGenerateChapterSummary:
    "Test chapter summary generation."

    def test_generate_with_approved_segments(self) -> None:
        "Test generating summary with approved segments."
        segments = [
            {"locked": True, "translation": "Translation one."},
            {"locked": True, "translation": "Translation two."},
            {"locked": False, "translation": None},
        ]

        summary = generate_chapter_summary(
            project_id="test-project",
            chapter_id="ch1",
            chapter_segments=segments,
        )

        assert summary.project_id == "test-project"
        assert summary.chapter_id == "ch1"
        assert "Translation one." in summary.summary
        assert "Translation two." in summary.summary
        assert summary.metadata["approved_count"] == 2
        assert summary.metadata["segment_count"] == 3

    def test_generate_with_no_approved_segments(self) -> None:
        "Test generating summary with no approved segments."
        segments = [
            {"locked": False, "translation": None},
            {"locked": False, "translation": None},
        ]

        summary = generate_chapter_summary(
            project_id="test-project",
            chapter_id="ch1",
            chapter_segments=segments,
        )

        assert "no approved segments" in summary.summary
        assert summary.metadata["approved_count"] == 0

    def test_max_tokens_enforcement(self) -> None:
        "Test max token enforcement."
        # Create segments with long translations
        long_text = "This is a very long segment. " * 100
        segments = [
            {"locked": True, "translation": long_text},
            {"locked": True, "translation": long_text},
        ]

        summary = generate_chapter_summary(
            project_id="test-project",
            chapter_id="ch1",
            chapter_segments=segments,
            max_tokens=50,
        )

        # Summary should be truncated
        assert summary.metadata["max_tokens"] == 50
        # 50 tokens * 4 chars/token = 200 chars max
        assert len(summary.summary) <= 250  # Allow some buffer


class TestSaveAndLoadChapterSummary:
    "Test chapter summary persistence."

    @pytest.fixture
    def temp_dir(self) -> Path:
        "Create temporary directory."
        return Path(tempfile.mkdtemp())

    def test_save_chapter_summary(self, temp_dir: Path) -> None:
        "Test saving chapter summary."
        summary = ChapterSummary(
            project_id="test-project",
            chapter_id="ch1",
            summary="Summary text",
            generated_at="2024-01-01T00:00:00",
        )

        saved_path = save_chapter_summary(summary, temp_dir)

        assert saved_path.exists()
        assert saved_path.name == "chapter_ch1.json"
        assert saved_path.parent.name == "summaries"

    def test_load_chapter_summary(self, temp_dir: Path) -> None:
        "Test loading chapter summary."
        summary = ChapterSummary(
            project_id="test-project",
            chapter_id="ch1",
            summary="Summary text",
            generated_at="2024-01-01T00:00:00",
        )
        save_chapter_summary(summary, temp_dir)

        loaded = load_chapter_summary("ch1", temp_dir)

        assert loaded is not None
        assert loaded.chapter_id == "ch1"
        assert loaded.summary == summary.summary

    def test_load_nonexistent_summary(self, temp_dir: Path) -> None:
        "Test loading nonexistent summary."
        loaded = load_chapter_summary("nonexistent", temp_dir)
        assert loaded is None

    def test_list_chapter_summaries(self, temp_dir: Path) -> None:
        "Test listing all chapter summaries."
        # Save multiple summaries
        for i in range(3):
            summary = ChapterSummary(
                project_id="test-project",
                chapter_id=f"ch{i}",
                summary=f"Summary {i}",
                generated_at="2024-01-01T00:00:00",
            )
            save_chapter_summary(summary, temp_dir)

        summaries = list_chapter_summaries(temp_dir)

        assert len(summaries) == 3
        assert all(isinstance(s, ChapterSummary) for s in summaries)

    def test_list_empty_summaries(self, temp_dir: Path) -> None:
        "Test listing when no summaries exist."
        summaries = list_chapter_summaries(temp_dir)
        assert len(summaries) == 0
