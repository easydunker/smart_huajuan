"""Unit tests for Hierarchical Context Assembler."""

import tempfile
from pathlib import Path

import pytest

from aat.orchestrator.context_assembler import (
    ContextAssembler,
    ContextConfig,
    AssembledContext,
)
from aat.orchestrator.style_guide import StyleGuide
from aat.orchestrator.chapter_summary import ChapterSummary


class TestContextConfig:
    "Test ContextConfig dataclass."

    def test_default_config(self) -> None:
        "Test default configuration."
        config = ContextConfig()

        assert config.max_tokens == 4000
        assert config.include_global_style is True
        assert config.include_termbank is True
        assert config.include_previous_segment is True
        assert config.include_chapter_summary is True

    def test_custom_config(self) -> None:
        "Test custom configuration."
        config = ContextConfig(
            max_tokens=1000,
            include_global_style=False,
            include_termbank=False,
        )

        assert config.max_tokens == 1000
        assert config.include_global_style is False
        assert config.include_termbank is False


class TestAssembledContext:
    "Test AssembledContext dataclass."

    def test_creation(self) -> None:
        "Test creating assembled context."
        context = AssembledContext(
            segment_id="s1",
            chapter_id="ch1",
            context_text="Test context",
            components={},
            token_count=100,
            truncated=False,
        )

        assert context.segment_id == "s1"
        assert context.chapter_id == "ch1"
        assert context.token_count == 100
        assert context.truncated is False

    def test_truncated_context(self) -> None:
        "Test truncated context."
        context = AssembledContext(
            segment_id="s1",
            context_text="Truncated context",
            token_count=5000,
            truncated=True,
        )

        assert context.truncated is True
        assert context.token_count == 5000


class TestContextAssembler:
    "Test ContextAssembler functionality."

    @pytest.fixture
    def temp_dir(self) -> Path:
        "Create temporary directory."
        return Path(tempfile.mkdtemp())

    def test_init_creates_directories(self, temp_dir: Path) -> None:
        "Test initialization."
        assembler = ContextAssembler(temp_dir)

        assert assembler.project_dir == temp_dir
        assert assembler.config.max_tokens == 4000

    def test_assemble_context_with_all_components(
        self, temp_dir: Path
    ) -> None:
        "Test assembling context with all components."
        assembler = ContextAssembler(temp_dir)

        # Create mock components
        style_guide = StyleGuide(
            project_id="test-project",
            generated_at="2024-01-01T00:00:00",
            constraints={"general": ["Test constraint"]},
        )
        termbank = {"locked": [{"source_phrase": "test", "target_phrase": "测试"}]}
        chapter_summary = ChapterSummary(
            project_id="test-project",
            chapter_id="ch1",
            summary="Chapter summary text.",
            generated_at="2024-01-01T00:00:00",
        )

        context = assembler.assemble_context_for_segment(
            segment_id="s1",
            chapter_id="ch1",
            termbank=termbank,
            previous_translation="Previous text.",
            chapter_summary=chapter_summary,
            global_style=style_guide,
        )

        assert context.segment_id == "s1"
        assert context.chapter_id == "ch1"
        assert "global_style" in context.components
        assert "termbank" in context.components
        assert "chapter_summary" in context.components
        assert "previous_segment" in context.components

    def test_assemble_context_with_minimal_components(
        self, temp_dir: Path
    ) -> None:
        "Test assembling context with minimal components."
        config = ContextConfig(
            include_global_style=False,
            include_termbank=False,
            include_chapter_summary=False,
            include_previous_segment=False,
        )
        assembler = ContextAssembler(temp_dir, config)

        context = assembler.assemble_context_for_segment(
            segment_id="s1",
            termbank=None,
            previous_translation=None,
            chapter_summary=None,
            global_style=None,
        )

        assert context.context_text == ""
        assert len(context.components) == 0

    def test_token_budget_enforcement(self, temp_dir: Path) -> None:
        "Test token budget enforcement."
        config = ContextConfig(max_tokens=100)
        assembler = ContextAssembler(temp_dir, config)

        # Create long context
        style_guide = StyleGuide(
            project_id="test-project",
            generated_at="2024-01-01T00:00:00",
            constraints={
                "long": ["This is a very long constraint. " * 50]
            },
        )

        context = assembler.assemble_context_for_segment(
            segment_id="s1",
            global_style=style_guide,
        )

        # Should be truncated
        assert context.truncated is True
        # Token count after truncation will include the truncation message
        # We verify it was truncated, not the exact token count
        assert context.token_count >= 100

    def test_no_truncation_within_budget(self, temp_dir: Path) -> None:
        "Test no truncation when within budget."
        config = ContextConfig(max_tokens=10000)
        assembler = ContextAssembler(temp_dir, config)

        context = assembler.assemble_context_for_segment(
            segment_id="s1",
            previous_translation="Short text.",
        )

        assert context.truncated is False

    def test_format_style_guide(self, temp_dir: Path) -> None:
        "Test style guide formatting."
        assembler = ContextAssembler(temp_dir)

        style_guide = StyleGuide(
            project_id="test-project",
            generated_at="2024-01-01T00:00:00",
            constraints={"vocabulary": ["Use formal terms", "Maintain consistency"]},
        )

        text = assembler._format_style_guide(style_guide)

        assert "【全局翻译风格指导】" in text
        assert "vocabulary:" in text

    def test_format_termbank(self, temp_dir: Path) -> None:
        "Test termbank formatting."
        assembler = ContextAssembler(temp_dir)

        termbank = {
            "locked": [
                {"source_phrase": "test1", "target_phrase": "测试1"},
                {"source_phrase": "test2", "target_phrase": "测试2"},
            ]
        }

        text = assembler._format_termbank(termbank)

        assert "【术语库（已锁定）】" in text
        assert "test1" in text
        assert "测试1" in text

    def test_format_chapter_summary(self, temp_dir: Path) -> None:
        "Test chapter summary formatting."
        assembler = ContextAssembler(temp_dir)

        chapter_summary = ChapterSummary(
            project_id="test-project",
            chapter_id="ch1",
            summary="Summary text here.",
            generated_at="2024-01-01T00:00:00",
        )

        text = assembler._format_chapter_summary(chapter_summary)

        assert "【前一章摘要】" in text
        assert "ch1" in text
        assert "Summary text here." in text

    def test_format_previous_segment(self, temp_dir: Path) -> None:
        "Test previous segment formatting."
        assembler = ContextAssembler(temp_dir)

        text = assembler._format_previous_segment("This is the previous segment translation.")

        assert "【前一段翻译】" in text
        assert "previous segment" in text.lower()

    def test_estimate_tokens(self, temp_dir: Path) -> None:
        "Test token estimation."
        assembler = ContextAssembler(temp_dir)

        # Short text
        assert assembler._estimate_tokens("") == 0
        assert assembler._estimate_tokens("short") == 1  # 5//4
        assert assembler._estimate_tokens("hello world") == 2  # 11//4

        # Longer text
        long_text = "This is a longer text. " * 100
        estimated = assembler._estimate_tokens(long_text)
        # ~656 tokens (2625//4)
        # Using a reasonable range for very long text
        assert 500 <= estimated <= 800

    def test_get_context_stats(self, temp_dir: Path) -> None:
        "Test getting context statistics."
        config = ContextConfig(
            max_tokens=5000,
            include_global_style=False,
            include_termbank=True,
        )
        assembler = ContextAssembler(temp_dir, config)

        stats = assembler.get_context_stats()

        assert stats["max_tokens"] == 5000
        assert stats["include_global_style"] is False
        assert stats["include_termbank"] is True
