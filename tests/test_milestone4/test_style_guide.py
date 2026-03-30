"""Unit tests for Global Style Guide Generator."""

import tempfile
from pathlib import Path

import pytest

from aat.orchestrator.style_guide import (
    StyleGuide,
    generate_style_guide,
    save_style_guide,
    load_style_guide,
)


class TestStyleGuide:
    """Test StyleGuide dataclass."""

    def test_creation(self) -> None:
        """Test creating a style guide."""
        style_guide = StyleGuide(
            project_id="test-project",
            generated_at="2024-01-01T00:00:00",
            constraints={
                "sentence_structure": ["Use clear sentences"],
                "vocabulary": ["Use formal terms"],
            },
        )

        assert style_guide.project_id == "test-project"
        assert len(style_guide.constraints) == 2
        assert "sentence_structure" in style_guide.constraints

    def test_to_dict_and_from_dict(self) -> None:
        """Test JSON serialization/deserialization."""
        original = StyleGuide(
            project_id="test-project",
            generated_at="2024-01-01T00:00:00",
            constraints={"general": ["Maintain academic tone"]},
        )

        data = original.to_dict()
        assert data["project_id"] == "test-project"
        assert "constraints" in data

        restored = StyleGuide.from_dict(data)
        assert restored.project_id == original.project_id
        assert restored.constraints == original.constraints

    def test_to_json_and_from_json(self) -> None:
        """Test JSON string serialization/deserialization."""
        original = StyleGuide(
            project_id="test-project",
            generated_at="2024-01-01T00:00:00",
            constraints={"general": ["Maintain academic tone"]},
        )

        json_str = original.to_json()
        assert isinstance(json_str, str)

        restored = StyleGuide.from_json(json_str)
        assert restored.project_id == original.project_id
        assert restored.constraints == original.constraints


class TestGenerateStyleGuide:
    """Test style guide generation."""

    def test_generate_chinese_style_guide(self) -> None:
        """Test generating Chinese academic style guide."""
        style_guide = generate_style_guide(
            project_id="test-project",
            target_language="zh",
            style_level="academic",
        )

        assert style_guide.project_id == "test-project"
        assert len(style_guide.constraints) > 0
        assert style_guide.metadata["target_language"] == "zh"
        assert style_guide.metadata["style_level"] == "academic"

    def test_generate_generic_style_guide(self) -> None:
        """Test generating generic style guide."""
        style_guide = generate_style_guide(
            project_id="test-project",
            target_language="en",
            style_level="academic",
        )

        assert style_guide.project_id == "test-project"
        assert "general" in style_guide.constraints
        assert style_guide.metadata["target_language"] == "en"

    def test_default_parameters(self) -> None:
        """Test default parameters."""
        style_guide = generate_style_guide(project_id="test-project")

        assert style_guide.metadata["target_language"] == "zh"
        assert style_guide.metadata["style_level"] == "academic"


class TestSaveAndLoadStyleGuide:
    """Test style guide persistence."""

    @pytest.fixture
    def temp_dir(self) -> Path:
        """Create temporary directory."""
        return Path(tempfile.mkdtemp())

    def test_save_style_guide(self, temp_dir: Path) -> None:
        """Test saving style guide to file."""
        style_guide = generate_style_guide(project_id="test-project")

        saved_path = save_style_guide(style_guide, temp_dir)

        assert saved_path.exists()
        assert saved_path.name == "global_style.json"
        assert saved_path.parent == temp_dir

    def test_load_style_guide(self, temp_dir: Path) -> None:
        """Test loading style guide from file."""
        style_guide = generate_style_guide(project_id="test-project")
        save_style_guide(style_guide, temp_dir)

        loaded = load_style_guide(temp_dir)

        assert loaded is not None
        assert loaded.project_id == style_guide.project_id
        assert loaded.constraints == style_guide.constraints

    def test_load_nonexistent_style_guide(self, temp_dir: Path) -> None:
        """Test loading nonexistent style guide."""
        loaded = load_style_guide(temp_dir)
        assert loaded is None
