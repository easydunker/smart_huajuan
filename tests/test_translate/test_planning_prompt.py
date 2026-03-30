"""Tests for pre-translation planning prompt functionality."""

import pytest

from aat.translate.prompts import PlanningPrompt


class TestPlanningPrompt:
    """Test suite for PlanningPrompt."""

    def test_planning_prompt_build_basic(self):
        """Test building planning prompt with basic input."""
        source_text = "Introduction: This study examines second dialect acquisition."

        messages = PlanningPrompt.build(
            source_text=source_text,
        )

        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert "规划" in messages[0]["content"]
        assert messages[1]["role"] == "user"
        assert source_text in messages[1]["content"]

    def test_planning_prompt_build_with_context(self):
        """Test building planning prompt with context."""
        source_text = "Chapter 1: Introduction"
        context_before = "Abstract"
        context_after = "Background"

        messages = PlanningPrompt.build(
            source_text=source_text,
            context_before=context_before,
            context_after=context_after,
        )

        user_content = messages[1]["content"]
        assert context_before in user_content
        assert context_after in user_content

    def test_planning_prompt_build_with_termbank(self):
        """Test building planning prompt with termbank."""
        source_text = "The study of SDA."
        termbank = {"SDA": "第二方言习得", "dialect": "方言"}

        messages = PlanningPrompt.build(
            source_text=source_text,
            termbank=termbank,
        )

        user_content = messages[1]["content"]
        assert "SDA" in user_content
        assert "第二方言习得" in user_content

    def test_planning_prompt_response_schema(self):
        """Test that response schema is correctly structured."""
        schema = PlanningPrompt.get_response_schema()

        assert schema["type"] == "object"
        assert "properties" in schema
        assert "segment_type" in schema["properties"]
        assert "key_terms" in schema["properties"]
        assert "special_formats" in schema["properties"]
        assert "translation_strategy" in schema["properties"]
        assert "required" in schema
        assert "segment_type" in schema["required"]

    def test_planning_prompt_segment_type_enum(self):
        """Test that segment type has correct enum values."""
        schema = PlanningPrompt.get_response_schema()

        segment_type_schema = schema["properties"]["segment_type"]
        assert "enum" in segment_type_schema
        expected_types = ["标题", "摘要", "引言", "方法", "结果", "讨论", "结论", "参考文献", "其他"]
        for t in expected_types:
            assert t in segment_type_schema["enum"]

    def test_planning_prompt_key_terms_structure(self):
        """Test that key_terms has correct structure."""
        schema = PlanningPrompt.get_response_schema()

        key_terms_schema = schema["properties"]["key_terms"]
        assert key_terms_schema["type"] == "array"
        item_schema = key_terms_schema["items"]
        assert "properties" in item_schema
        assert "term" in item_schema["properties"]
        assert "context" in item_schema["properties"]
        assert "suggested_translation" in item_schema["properties"]


class TestPlanningPipelineIntegration:
    """Test integration of planning into pipeline."""

    def test_planning_state_exists(self):
        """Test that PLANNING state is defined in SegmentState."""
        from aat.storage.models import SegmentState

        # Check that PLANNING is a valid state
        assert hasattr(SegmentState, 'PLANNING')
        assert SegmentState.PLANNING.value == "planning"

    def test_segment_can_store_planning_analysis(self):
        """Test that segment metadata can store planning analysis."""
        from aat.storage.models import Segment, Paragraph

        # Create a segment with metadata
        segment = Segment(
            sid="test-1",
            pid_list=["p1"],
            source_text="Test content",
            metadata={
                "planning_analysis": {
                    "segment_type": "引言",
                    "key_terms": [{"term": "test", "suggested_translation": "测试"}],
                    "special_formats": [],
                    "translation_strategy": "保持学术语气"
                }
            }
        )

        assert "planning_analysis" in segment.metadata
        assert segment.metadata["planning_analysis"]["segment_type"] == "引言"