"""Tests for data models."""

import pytest
from aat.storage.models import (
    Citation,
    DocumentModel,
    FeedbackCategory,
    Paragraph,
    ProjectPreferences,
    Reference,
    Section,
    Segment,
    SegmentState,
    StructuredFeedback,
    StylePreference,
    TermBank,
    TranslationSegment,
    ValidationResult,
    ValidatorStatus,
)


class TestCitation:
    """Test Citation model."""

    def test_create_citation(self) -> None:
        """Test creating a citation."""
        citation = Citation(cid="c1", text="(Smith, 2020)", pid="p1")
        assert citation.cid == "c1"
        assert citation.text == "(Smith, 2020)"
        assert citation.pid == "p1"


class TestReference:
    """Test Reference model."""

    def test_create_reference(self) -> None:
        """Test creating a reference."""
        ref = Reference(rid="r1", raw="Smith, J. (2020). Title.")
        assert ref.rid == "r1"
        assert ref.raw == "Smith, J. (2020). Title."


class TestParagraph:
    """Test Paragraph model."""

    def test_create_paragraph(self) -> None:
        """Test creating a paragraph."""
        para = Paragraph(pid="p1", text="This is a paragraph.")
        assert para.pid == "p1"
        assert para.text == "This is a paragraph."
        assert len(para.citations) == 0

    def test_paragraph_with_citations(self) -> None:
        """Test creating a paragraph with citations."""
        citation = Citation(cid="c1", text="(Smith, 2020)", pid="p1")
        para = Paragraph(pid="p1", text="This is a paragraph.", citations=[citation])
        assert len(para.citations) == 1
        assert para.citations[0].cid == "c1"


class TestSection:
    """Test Section model."""

    def test_create_section(self) -> None:
        """Test creating a section."""
        section = Section(heading="Introduction", paragraphs=[])
        assert section.heading == "Introduction"
        assert len(section.paragraphs) == 0

    def test_create_section_without_heading(self) -> None:
        """Test creating a section without heading."""
        section = Section(heading=None, paragraphs=[])
        assert section.heading is None


class TestDocumentModel:
    """Test DocumentModel."""

    def test_create_empty_document(self) -> None:
        """Test creating an empty document."""
        doc = DocumentModel.create()
        assert doc.doc_id
        assert doc.title is None
        assert len(doc.sections) == 0
        assert len(doc.references) == 0
        assert len(doc.citations) == 0

    def test_create_document_with_content(self) -> None:
        """Test creating a document with content."""
        para = Paragraph(pid="p1", text="Test paragraph.")
        section = Section(heading="Test", paragraphs=[para])
        doc = DocumentModel(
            doc_id="test-doc",
            title="Test Document",
            sections=[section],
            references=[],
            citations=[],
        )
        assert doc.doc_id == "test-doc"
        assert doc.title == "Test Document"
        assert len(doc.sections) == 1
        assert doc.sections[0].heading == "Test"


class TestSegment:
    """Test Segment model."""

    def test_create_segment(self) -> None:
        """Test creating a segment."""
        segment = Segment(
            sid="s1",
            pid_list=["p1", "p2"],
            source_text="This is segment text.",
        )
        assert segment.sid == "s1"
        assert segment.pid_list == ["p1", "p2"]
        assert segment.source_text == "This is segment text."
        assert segment.context_before is None

    def test_segment_with_context(self) -> None:
        """Test creating a segment with context."""
        segment = Segment(
            sid="s1",
            pid_list=["p1"],
            source_text="Text.",
            context_before="Before",
            context_after="After",
        )
        assert segment.context_before == "Before"
        assert segment.context_after == "After"


class TestValidationResult:
    """Test ValidationResult."""

    def test_pass_result(self) -> None:
        """Test creating a passing validation result."""
        result = ValidationResult(status=ValidatorStatus.PASS)
        assert result.is_pass()
        assert not result.is_fail()
        assert not result.is_flag()

    def test_fail_result(self) -> None:
        """Test creating a failing validation result."""
        result = ValidationResult(
            status=ValidatorStatus.FAIL,
            issues=[{"code": "ERROR", "detail": "Something went wrong"}],
        )
        assert result.is_fail()
        assert not result.is_pass()
        assert len(result.issues) == 1

    def test_flag_result(self) -> None:
        """Test creating a flagged validation result."""
        result = ValidationResult(status=ValidatorStatus.FLAG)
        assert result.is_flag()
        assert not result.is_pass()


class TestSegmentState:
    """Test SegmentState enum."""

    def test_segment_state_is_enum(self) -> None:
        """SegmentState values should be instances of both SegmentState and str."""
        assert isinstance(SegmentState.ASSEMBLE_CONTEXT, SegmentState)
        assert isinstance(SegmentState.ASSEMBLE_CONTEXT, str)

    def test_segment_state_values(self) -> None:
        """Each SegmentState member should have the expected string value."""
        assert SegmentState.ASSEMBLE_CONTEXT.value == "assemble_context"
        assert SegmentState.PLANNING.value == "planning"
        assert SegmentState.DRAFT_TRANSLATE.value == "draft_translate"
        assert SegmentState.DETERMINISTIC_VALIDATE.value == "deterministic_validate"
        assert SegmentState.LLM_CRITIC_REVIEW.value == "llm_critic_review"
        assert SegmentState.UNCERTAINTY_DETECT.value == "uncertainty_detect"
        assert SegmentState.USER_FEEDBACK_WAIT.value == "user_feedback_wait"
        assert SegmentState.REVISE.value == "revise"
        assert SegmentState.LOCK_SEGMENT.value == "lock_segment"

    def test_segment_state_not_dataclass(self) -> None:
        """SegmentState should NOT have __dataclass_fields__ (no @dataclass)."""
        assert not hasattr(SegmentState, "__dataclass_fields__")


class TestTermBank:
    """Test TermBank."""

    def test_create_empty_termbank(self) -> None:
        """Test creating an empty termbank."""
        bank = TermBank()
        assert len(bank.items) == 0

    def test_add_term(self) -> None:
        """Test adding a term to the termbank."""
        bank = TermBank()
        bank.add_term("machine learning", "机器学习", confidence=0.9)
        assert len(bank.items) == 1
        assert bank.items[0].source_term == "machine learning"
        assert bank.items[0].target_term == "机器学习"
        assert bank.items[0].confidence == 0.9

    def test_add_term_with_examples(self) -> None:
        """Test adding a term with examples."""
        bank = TermBank()
        examples = [
            {"source": "We use machine learning for...", "quote": "我们使用机器学习进行..."},
        ]
        bank.add_term("machine learning", "机器学习", examples=examples)
        assert len(bank.items[0].examples) == 1


class TestFeedbackCategory:
    """Test FeedbackCategory enum."""

    def test_feedback_category_enum_values(self) -> None:
        """All expected categories should exist with correct string values."""
        assert FeedbackCategory.WRONG_TERMINOLOGY.value == "wrong_terminology"
        assert FeedbackCategory.MEANING_DRIFT.value == "meaning_drift"
        assert FeedbackCategory.TONE_ISSUE.value == "tone_issue"
        assert FeedbackCategory.OMISSION.value == "omission"
        assert FeedbackCategory.ADDITION.value == "addition"
        assert FeedbackCategory.STYLE.value == "style"
        assert FeedbackCategory.OTHER.value == "other"


class TestStructuredFeedback:
    """Test StructuredFeedback dataclass."""

    def test_structured_feedback_creation(self) -> None:
        """Create StructuredFeedback with required fields."""
        fb = StructuredFeedback(
            category=FeedbackCategory.OMISSION,
            detail="Missing sentence",
        )
        assert fb.category == FeedbackCategory.OMISSION
        assert fb.detail == "Missing sentence"

    def test_structured_feedback_optional_fields(self) -> None:
        """Optional fields should default to None."""
        fb = StructuredFeedback(
            category=FeedbackCategory.OTHER,
            detail="test",
        )
        assert fb.span is None
        assert fb.suggested_fix is None
        assert fb.timestamp is None


class TestStylePreference:
    """Test StylePreference dataclass."""

    def test_style_preference_creation(self) -> None:
        """Create StylePreference with defaults."""
        sp = StylePreference(key="tone", value="academic")
        assert sp.key == "tone"
        assert sp.value == "academic"
        assert sp.scope == "global"


class TestProjectPreferences:
    """Test ProjectPreferences dataclass."""

    def test_project_preferences_defaults(self) -> None:
        """Empty ProjectPreferences should have empty dict and empty list."""
        pp = ProjectPreferences()
        assert pp.terminology_overrides == {}
        assert pp.style_preferences == []

    def test_project_preferences_with_overrides(self) -> None:
        """Construct with terminology_overrides."""
        pp = ProjectPreferences(terminology_overrides={"entropy": "熵"})
        assert pp.terminology_overrides["entropy"] == "熵"


class TestTranslationSegmentNewFields:
    """Test new fields on TranslationSegment."""

    def test_translation_segment_has_structured_feedback(self) -> None:
        """structured_feedback should default to empty list."""
        ts = TranslationSegment(
            segment=Segment(sid="s1", pid_list=["p1"], source_text="test"),
            state=SegmentState.DRAFT_TRANSLATE,
        )
        assert ts.structured_feedback == []

    def test_translation_segment_has_revision_requested(self) -> None:
        """revision_requested should default to False."""
        ts = TranslationSegment(
            segment=Segment(sid="s1", pid_list=["p1"], source_text="test"),
            state=SegmentState.DRAFT_TRANSLATE,
        )
        assert ts.revision_requested is False
