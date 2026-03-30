"""Unit tests for Translation Memory (TM)."""

import pytest
from datetime import datetime, timedelta

from aat.translate.translation_memory import TMEntry, TranslationMemory


class TestTMEntry:
    """Test TMEntry dataclass."""

    def test_creation(self) -> None:
        """Test creating a TM entry."""
        entry = TMEntry(
            source_phrase="machine learning",
            normalized_key="machine learning",
            target_phrase="机器学习",
            confidence=0.95,
        )

        assert entry.source_phrase == "machine learning"
        assert entry.normalized_key == "machine learning"
        assert entry.target_phrase == "机器学习"
        assert entry.confidence == 0.95
        assert not entry.locked
        assert not entry.first_used_chapter


class TestTranslationMemory:
    """Test TranslationMemory operations."""

    def test_add_entry(self) -> None:
        """Test adding entries to memory."""
        memory = TranslationMemory(project_id="test-project")
        assert len(memory.entries) == 0

        # Add first entry
        entry1 = TMEntry(
            source_phrase="machine learning",
            normalized_key="machine learning",
            target_phrase="机器学习",
        )

        memory.add_entry(entry1)
        assert len(memory.entries) == 1

        # Add second entry
        entry2 = TMEntry(
            source_phrase="deep learning",
            normalized_key="deep learning",
            target_phrase="深度学习",
        )

        memory.add_entry(entry2)
        assert len(memory.entries) == 2

    def test_find_entry(self) -> None:
        """Test finding entries."""
        memory = TranslationMemory(project_id="test-project")

        entry1 = TMEntry(
            source_phrase="machine learning",
            normalized_key="machine learning",
            target_phrase="机器学习",
        )

        memory.add_entry(entry1)

        # Find exact match
        found = memory.find_entry("machine learning")
        assert found is not None
        assert found.target_phrase == "机器学习"

        # Find non-existent
        not_found = memory.find_entry("non existent phrase")
        assert not_found is None

    def test_find_by_chapter(self) -> None:
        """Test finding entries by chapter."""
        memory = TranslationMemory(project_id="test-project")

        entry1 = TMEntry(
            source_phrase="machine learning",
            normalized_key="machine learning",
            target_phrase="机器学习",
            first_used_chapter="ch1",
        )

        entry2 = TMEntry(
            source_phrase="machine learning",
            normalized_key="machine learning",
            target_phrase="机器学习",
            first_used_chapter="ch2",
        )

        memory.add_entry(entry1)
        memory.add_entry(entry2)

        # Find all from ch1
        ch1_entries = memory.find_entries_by_chapter("ch1")
        assert len(ch1_entries) == 1
        assert ch1_entries[0].first_used_chapter == "ch1"

        # Find all from ch2
        ch2_entries = memory.find_entries_by_chapter("ch2")
        assert len(ch2_entries) == 1
        assert ch2_entries[0].first_used_chapter == "ch2"

    def test_to_dict_and_from_dict(self) -> None:
        """Test JSON serialization/deserialization."""
        memory = TranslationMemory(project_id="test-project")

        entry = TMEntry(
            source_phrase="machine learning",
            normalized_key="machine learning",
            target_phrase="机器学习",
            confidence=0.8,
        )

        memory.add_entry(entry)

        # Convert to dict
        data = memory.to_dict()

        assert data["project_id"] == "test-project"
        assert len(data["entries"]) == 1
        assert data["entries"][0]["source_phrase"] == "machine learning"

        # Convert back from dict
        restored = TranslationMemory.from_dict(data)

        assert restored.project_id == memory.project_id
        assert len(restored.entries) == len(memory.entries)
        assert restored.entries[0].source_phrase == memory.entries[0].source_phrase
