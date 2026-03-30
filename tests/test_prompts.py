"""Tests for translation prompts."""

import pytest

from aat.translate.prompts import (
    CriticReviewPrompt,
    DraftTranslationPrompt,
    RevisionPrompt,
)


class TestDraftTranslationPrompt:
    """Test DraftTranslationPrompt."""

    def test_build_basic_prompt(self) -> None:
        """Test building basic prompt without context or termbank."""
        messages = DraftTranslationPrompt.build(
            source_text="Test text.",
        )

        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert "学术翻译专家" in messages[0]["content"]
        assert messages[1]["role"] == "user"
        assert "Test text." in messages[1]["content"]

    def test_build_with_context(self) -> None:
        """Test building prompt with context."""
        messages = DraftTranslationPrompt.build(
            source_text="Test text.",
            context_before="Previous paragraph.",
            context_after="Next paragraph.",
        )

        assert "前文：Previous paragraph." in messages[1]["content"]
        assert "后文：Next paragraph." in messages[1]["content"]

    def test_build_with_termbank(self) -> None:
        """Test building prompt with termbank."""
        messages = DraftTranslationPrompt.build(
            source_text="Test text.",
            termbank={"machine learning": "机器学习", "deep learning": "深度学习"},
        )

        assert "术语翻译" in messages[1]["content"]
        assert "machine learning" in messages[1]["content"]
        assert "机器学习" in messages[1]["content"]

    def test_get_response_schema(self) -> None:
        """Test getting response schema."""
        schema = DraftTranslationPrompt.get_response_schema()

        assert "translation" in schema["properties"]
        assert "uncertainties" in schema["properties"]
        assert "translation" in schema["required"]
        assert "uncertainties" in schema["required"]
        assert "notes" in schema["required"]


class TestContextSeparation:
    """Tests for context_before/context_after not being duplicated."""

    def test_planning_prompt_separates_context_before_and_after(self) -> None:
        """context_before and context_after should each appear exactly once."""
        from aat.translate.prompts import PlanningPrompt

        messages = PlanningPrompt.build(
            source_text="test",
            context_before="before text",
            context_after="after text",
        )

        user_content = messages[1]["content"]
        assert user_content.count("before text") == 1
        assert user_content.count("after text") == 1

    def test_draft_prompt_separates_context_before_and_after(self) -> None:
        """context_before and context_after should each appear exactly once."""
        messages = DraftTranslationPrompt.build(
            source_text="test",
            context_before="before text",
            context_after="after text",
        )

        user_content = messages[1]["content"]
        assert user_content.count("before text") == 1
        assert user_content.count("after text") == 1


class TestDraftTranslationPromptPlanning:
    """Test that planning analysis is included in the draft prompt."""

    def test_draft_prompt_includes_planning_analysis(self) -> None:
        """Planning analysis data should appear in the user message."""
        messages = DraftTranslationPrompt.build(
            source_text="test",
            planning_analysis={
                "segment_type": "方法",
                "translation_strategy": "keep formal",
            },
        )

        user_content = messages[1]["content"]
        assert "方法" in user_content
        assert "keep formal" in user_content


class TestCriticReviewPrompt:
    """Test CriticReviewPrompt."""

    def test_build_basic_prompt(self) -> None:
        """Test building basic critic prompt."""
        messages = CriticReviewPrompt.build(
            source_text="Original text.",
            translation="Translated text.",
        )

        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert "学术翻译审稿人" in messages[0]["content"]
        assert messages[1]["role"] == "user"

        content = messages[1]["content"]
        assert "Original text." in content
        assert "Translated text." in content

    def test_get_response_schema(self) -> None:
        """Test getting response schema."""
        schema = CriticReviewPrompt.get_response_schema()

        assert "issues" in schema["properties"]
        assert schema["required"] == ["issues"]


class TestRevisionPrompt:
    """Test RevisionPrompt."""

    def test_build_basic_prompt(self) -> None:
        """Test building basic revision prompt."""
        messages = RevisionPrompt.build(
            source_text="Original.",
            current_translation="Current.",
            critic_issues=[],
            user_feedback=[],
            user_answers={},
        )

        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert "修订" in messages[0]["content"]

    def test_build_with_critic_issues(self) -> None:
        """Test building revision prompt with critic issues."""
        critic_issues = [
            {"code": "MEANING_DRIFT", "detail": "Changed meaning"},
        ]

        messages = RevisionPrompt.build(
            source_text="Original.",
            current_translation="Current.",
            critic_issues=critic_issues,
            user_feedback=[],
            user_answers={},
        )

        content = messages[1]["content"]
        assert "MEANING_DRIFT" in content
        assert "Changed meaning" in content

    def test_build_with_user_feedback(self) -> None:
        """Test building revision prompt with user feedback."""
        user_feedback = ["The tone should be more formal."]

        messages = RevisionPrompt.build(
            source_text="Original.",
            current_translation="Current.",
            user_feedback=user_feedback,
            critic_issues=[],
            user_answers={},
        )

        content = messages[1]["content"]
        assert "formal" in content

    def test_build_with_user_answers(self) -> None:
        """Test building revision prompt with user answers."""
        user_answers = {"What is this?": "Option A"}

        messages = RevisionPrompt.build(
            source_text="Original.",
            current_translation="Current.",
            user_answers=user_answers,
            critic_issues=[],
            user_feedback=[],
        )

        content = messages[1]["content"]
        assert "What is this?" in content
        assert "Option A" in content

    def test_revision_prompt_accepts_structured_feedback(self) -> None:
        """Structured feedback should appear in the revision user message."""
        messages = RevisionPrompt.build(
            source_text="Original.",
            current_translation="Current.",
            critic_issues=[],
            user_feedback=[],
            user_answers={},
            structured_feedback=[{"category": "OMISSION", "detail": "Missing sentence"}],
        )
        content = messages[1]["content"]
        assert "OMISSION" in content
        assert "Missing sentence" in content

    def test_revision_prompt_accepts_style_preferences(self) -> None:
        """Style preferences should appear in the revision user message."""
        messages = RevisionPrompt.build(
            source_text="Original.",
            current_translation="Current.",
            critic_issues=[],
            user_feedback=[],
            user_answers={},
            style_preferences={"formality": "formal", "tone": "academic"},
        )
        content = messages[1]["content"]
        assert "formal" in content
        assert "academic" in content

    def test_revision_prompt_structured_feedback_none_is_ok(self) -> None:
        """structured_feedback=None should not raise an error."""
        messages = RevisionPrompt.build(
            source_text="Original.",
            current_translation="Current.",
            critic_issues=[],
            user_feedback=[],
            user_answers={},
            structured_feedback=None,
        )
        assert len(messages) == 2

    def test_revision_prompt_style_preferences_none_is_ok(self) -> None:
        """style_preferences=None should not raise an error."""
        messages = RevisionPrompt.build(
            source_text="Original.",
            current_translation="Current.",
            critic_issues=[],
            user_feedback=[],
            user_answers={},
            style_preferences=None,
        )
        assert len(messages) == 2

    def test_existing_revision_prompt_build_unchanged(self) -> None:
        """Calling build() with only original params should still work."""
        messages = RevisionPrompt.build(
            source_text="Original.",
            current_translation="Current.",
            critic_issues=[],
            user_feedback=[],
            user_answers={},
        )
        assert len(messages) == 2
        assert messages[0]["role"] == "system"

    def test_draft_prompt_accepts_style_preferences(self) -> None:
        """Style preferences with terminology_overrides should appear in draft prompt."""
        messages = DraftTranslationPrompt.build(
            source_text="test",
            style_preferences={"terminology_overrides": {"entropy": "熵"}},
        )
        content = messages[1]["content"]
        assert "entropy" in content
        assert "熵" in content

    def test_draft_prompt_merges_term_overrides_into_termbank(self) -> None:
        """Both termbank and terminology_overrides should appear in the prompt."""
        messages = DraftTranslationPrompt.build(
            source_text="test",
            termbank={"foo": "bar"},
            style_preferences={"terminology_overrides": {"baz": "qux"}},
        )
        content = messages[1]["content"]
        assert "foo" in content
        assert "bar" in content
        assert "baz" in content
        assert "qux" in content
