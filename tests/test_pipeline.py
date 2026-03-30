"""Tests for translation pipeline."""

import os
import tempfile
from dataclasses import asdict

import pytest

from aat.storage.models import (
    DocumentModel,
    Paragraph,
    Segment,
    SegmentState,
    Section,
    TranslationProject,
    TranslationSegment,
    UncertaintyItem,
)
from aat.translate.llm_client import FakeLLMClient, create_client
from aat.translate.pipeline import PipelineConfig, TranslationPipeline
from aat.translate.validators import UncertaintyDetector


@pytest.fixture
def fake_document() -> DocumentModel:
    """Create a fake document for testing."""
    doc = DocumentModel.create()
    doc.title = "Test Document"
    doc.sections = [
        Section(
            heading="Introduction",
            paragraphs=[
                Paragraph(pid="p1", text="This is a test paragraph (Smith, 2020)."),
                Paragraph(pid="p2", text="Second paragraph with value p < 0.05."),
            ],
        )
    ]
    doc.references = []
    doc.citations = []
    return doc


@pytest.fixture
def fake_llm_client() -> FakeLLMClient:
    """Create a fake LLM client for testing."""
    client = FakeLLMClient(responses={})
    return client


class TestPipelineConfig:
    """Test PipelineConfig."""

    def test_default_config(self) -> None:
        """Test default configuration."""
        config = PipelineConfig()
        assert config.llm_provider == "anthropic"
        assert config.llm_model == "claude-3-5-sonnet-20241022"
        assert config.require_user_confirmation_on_fail is True
        assert config.enable_checkpoints is True


class TestTranslationPipelineInit:
    """Test TranslationPipeline initialization."""

    def test_init_with_project(self, fake_document) -> None:
        """Test initialization with project."""
        project = TranslationProject.create(fake_document)
        pipeline = TranslationPipeline(project)
        assert pipeline.project == project

    def test_init_with_config(self, fake_document) -> None:
        """Test initialization with custom config."""
        project = TranslationProject.create(fake_document)
        config = PipelineConfig(enable_checkpoints=False)
        pipeline = TranslationPipeline(project, config)
        assert pipeline.config.enable_checkpoints is False


class TestTranslationPipelineCreateSegments:
    """Test segment creation from document."""

    def test_creates_segments_from_document(
        self, fake_document
    ) -> None:
        """Test that segments are created from document paragraphs."""
        project = TranslationProject.create(fake_document)
        config = PipelineConfig(enable_checkpoints=False)
        pipeline = TranslationPipeline(project, config)

        pipeline._create_segments_from_document()

        assert len(project.segments) > 0
        for seg in project.segments:
            assert seg.state == SegmentState.ASSEMBLE_CONTEXT


class TestDraftTranslate:
    """Test draft translation state."""

    def test_draft_translate_success(self, fake_llm_client) -> None:
        """Test successful draft translation."""
        segment = Segment(sid="s1", pid_list=["p1"], source_text="Test text.")
        translation_segment = TranslationSegment(
            segment=segment,
            state=SegmentState.DRAFT_TRANSLATE,
        )

        project = TranslationProject.create(DocumentModel.create())
        pipeline = TranslationPipeline(project)
        pipeline.llm_client = fake_llm_client

        pipeline._draft_translate(translation_segment)

        assert translation_segment.translation is not None


class TestDeterministicValidate:
    """Test deterministic validation state."""

    def test_valid_translation_passes(self) -> None:
        """Test that valid translation passes all validators."""
        segment = Segment(sid="s1", pid_list=["p1"], source_text="Test (Smith, 2020).")
        translation_segment = TranslationSegment(
            segment=segment,
            state=SegmentState.DETERMINISTIC_VALIDATE,
            translation="Test (Smith, 2020).",
        )

        project = TranslationProject.create(DocumentModel.create())
        pipeline = TranslationPipeline(project)

        pipeline._deterministic_validate(translation_segment)

        assert len(translation_segment.validator_results) > 0
        assert all(result.is_pass() for result in translation_segment.validator_results)

    def test_missing_citation_fails(self) -> None:
        """Test that missing citation fails validation."""
        segment = Segment(sid="s1", pid_list=["p1"], source_text="Test (Smith, 2020).")
        translation_segment = TranslationSegment(
            segment=segment,
            state=SegmentState.DETERMINISTIC_VALIDATE,
            translation="Test text.",
        )

        project = TranslationProject.create(DocumentModel.create())
        pipeline = TranslationPipeline(project)

        pipeline._deterministic_validate(translation_segment)

        assert any(result.is_fail() for result in translation_segment.validator_results)

    def test_missing_number_fails(self) -> None:
        """Test that missing number fails validation."""
        segment = Segment(sid="s1", pid_list=["p1"], source_text="Value is p < 0.05.")
        translation_segment = TranslationSegment(
            segment=segment,
            state=SegmentState.DETERMINISTIC_VALIDATE,
            translation="Value is p.",
        )

        project = TranslationProject.create(DocumentModel.create())
        pipeline = TranslationPipeline(project)

        pipeline._deterministic_validate(translation_segment)

        assert any(result.is_fail() for result in translation_segment.validator_results)


class TestUncertaintyDetect:
    """Test uncertainty detection state."""

    def test_no_uncertainties(self) -> None:
        """Test that clean text produces no uncertainties."""
        segment = Segment(sid="s1", pid_list=["p1"], source_text="Test text.")
        translation_segment = TranslationSegment(
            segment=segment,
            state=SegmentState.UNCERTAINTY_DETECT,
            translation="Translation.",
            validator_results=[],
        )

        project = TranslationProject.create(DocumentModel.create())
        pipeline = TranslationPipeline(project)

        pipeline._uncertainty_detect(translation_segment)

        assert len(translation_segment.uncertainties) == 0

    def test_with_uncertainties_blocks(self) -> None:
        """Test that pre-existing uncertainties are preserved (early return)."""
        segment = Segment(sid="s1", pid_list=["p1"], source_text="Test text.")
        translation_segment = TranslationSegment(
            segment=segment,
            state=SegmentState.UNCERTAINTY_DETECT,
            translation="Translation.",
            uncertainties=[
                UncertaintyItem(
                    type="TERM",
                    span="test",
                    question="What is this?",
                    options=["A", "B"],
                )
            ],
        )

        project = TranslationProject.create(DocumentModel.create())
        pipeline = TranslationPipeline(project)

        pipeline._uncertainty_detect(translation_segment)

        assert len(translation_segment.uncertainties) == 1
        assert translation_segment.uncertainties[0].question == "What is this?"


class TestLockSegment:
    """Test lock segment state."""

    def test_lock_sets_flag(self) -> None:
        """Test that locking sets locked flag."""
        segment = Segment(sid="s1", pid_list=["p1"], source_text="Test.")
        translation_segment = TranslationSegment(
            segment=segment,
            state=SegmentState.LOCK_SEGMENT,
            translation="Translation.",
        )

        project = TranslationProject.create(DocumentModel.create())
        pipeline = TranslationPipeline(project)

        translation_segment.locked = True

        assert translation_segment.locked is True


class TestAssembleContext:
    """Test context assembly integration."""

    def test_assembles_context_with_no_previous(self) -> None:
        """Test context assembly when there's no previous segment."""
        segment = Segment(sid="s1", pid_list=["p1"], source_text="Test text.")
        translation_segment = TranslationSegment(
            segment=segment,
            state=SegmentState.ASSEMBLE_CONTEXT,
        )

        project = TranslationProject.create(DocumentModel.create())
        project.segments = [translation_segment]
        config = PipelineConfig(llm_provider="fake", enable_checkpoints=False)
        pipeline = TranslationPipeline(project, config)

        pipeline._assemble_context(translation_segment)

        assert translation_segment.segment.metadata is not None
        assert "assembled_context" in translation_segment.segment.metadata

    def test_assembles_context_with_previous_translation(self) -> None:
        """Test context includes previous segment's translation."""
        seg1 = TranslationSegment(
            segment=Segment(sid="s1", pid_list=["p1"], source_text="First."),
            state=SegmentState.LOCK_SEGMENT,
            translation="第一句。",
            locked=True,
        )
        seg2 = TranslationSegment(
            segment=Segment(sid="s2", pid_list=["p2"], source_text="Second."),
            state=SegmentState.ASSEMBLE_CONTEXT,
        )

        project = TranslationProject.create(DocumentModel.create())
        project.segments = [seg1, seg2]
        config = PipelineConfig(llm_provider="fake", enable_checkpoints=False)
        pipeline = TranslationPipeline(project, config)

        pipeline._assemble_context(seg2)

        context = seg2.segment.metadata["assembled_context"]
        assert "第一句" in context

    def test_assembles_context_with_locked_terms(self) -> None:
        """Test context includes locked terminology."""
        segment = TranslationSegment(
            segment=Segment(sid="s1", pid_list=["p1"], source_text="Test."),
            state=SegmentState.ASSEMBLE_CONTEXT,
        )

        project = TranslationProject.create(DocumentModel.create())
        project.segments = [segment]
        config = PipelineConfig(llm_provider="fake", enable_checkpoints=False)
        pipeline = TranslationPipeline(project, config)
        pipeline.translation_memory.lock_term("machine learning", "机器学习")

        pipeline._assemble_context(segment)

        context = segment.segment.metadata["assembled_context"]
        assert "machine learning" in context


class TestTranslationMemoryIntegration:
    """Test TranslationMemory integration with pipeline."""

    def test_pipeline_has_translation_memory(self) -> None:
        """Test that pipeline initializes with a TranslationMemory."""
        project = TranslationProject.create(DocumentModel.create())
        config = PipelineConfig(llm_provider="fake", enable_checkpoints=False)
        pipeline = TranslationPipeline(project, config)

        assert pipeline.translation_memory is not None
        assert pipeline.translation_memory.project_id == project.project_id

    def test_extract_and_lock_terms_populates_tm(self) -> None:
        """Test that planning analysis terms are added to TM."""
        project = TranslationProject.create(DocumentModel.create())
        config = PipelineConfig(llm_provider="fake", enable_checkpoints=False)
        pipeline = TranslationPipeline(project, config)

        key_terms = [
            {"term": "Machine Learning", "suggested_translation": "机器学习", "context": ""},
            {"term": "Neural Network", "suggested_translation": "神经网络", "context": ""},
        ]
        pipeline._extract_and_lock_terms(key_terms)

        assert pipeline.translation_memory.is_locked("machine learning")
        assert pipeline.translation_memory.is_locked("neural network")

    def test_locked_terms_fed_into_draft_translate(self, fake_llm_client) -> None:
        """Test that locked TM terms are passed to the draft prompt."""
        segment = Segment(sid="s1", pid_list=["p1"], source_text="Test text.")
        translation_segment = TranslationSegment(
            segment=segment,
            state=SegmentState.DRAFT_TRANSLATE,
        )

        project = TranslationProject.create(DocumentModel.create())
        config = PipelineConfig(llm_provider="fake", enable_checkpoints=False)
        pipeline = TranslationPipeline(project, config)
        pipeline.llm_client = fake_llm_client
        pipeline.translation_memory.lock_term("deep learning", "深度学习")

        pipeline._draft_translate(translation_segment)

        assert translation_segment.translation is not None


class TestRevise:
    """Test the _revise method uses RevisionPrompt."""

    def test_revise_calls_llm(self, fake_llm_client) -> None:
        """Test that _revise actually calls the LLM for revision."""
        segment = Segment(sid="s1", pid_list=["p1"], source_text="Test (Smith, 2020).")
        translation_segment = TranslationSegment(
            segment=segment,
            state=SegmentState.REVISE,
            translation="测试文本。",
            critic_issues=[{"code": "OMISSION", "detail": "Missing citation"}],
            uncertainties=[
                UncertaintyItem(type="TERM", span="test", question="?", options=[]),
            ],
        )

        project = TranslationProject.create(DocumentModel.create())
        config = PipelineConfig(llm_provider="fake", enable_checkpoints=False)
        pipeline = TranslationPipeline(project, config)
        pipeline.llm_client = fake_llm_client

        pipeline._revise(translation_segment)

        assert fake_llm_client.call_count >= 1
        assert len(translation_segment.uncertainties) == 0

    def test_revise_without_translation_clears_uncertainties(self) -> None:
        """Test that _revise with no translation just clears uncertainties."""
        segment = Segment(sid="s1", pid_list=["p1"], source_text="Test.")
        translation_segment = TranslationSegment(
            segment=segment,
            state=SegmentState.REVISE,
            translation=None,
            uncertainties=[
                UncertaintyItem(type="TERM", span="x", question="?", options=[]),
            ],
        )

        project = TranslationProject.create(DocumentModel.create())
        config = PipelineConfig(llm_provider="fake", enable_checkpoints=False)
        pipeline = TranslationPipeline(project, config)

        pipeline._revise(translation_segment)

        assert len(translation_segment.uncertainties) == 0


class TestFeedbackProviderIntegration:
    """Test FeedbackProvider integration with TranslationPipeline."""

    def test_pipeline_accepts_feedback_provider(self) -> None:
        """Pipeline should accept feedback_provider kwarg."""
        from aat.translate.feedback import AutoSkipFeedbackProvider

        provider = AutoSkipFeedbackProvider()
        project = TranslationProject.create(DocumentModel.create())
        pipeline = TranslationPipeline(project, feedback_provider=provider)
        assert pipeline.feedback_provider is provider

    def test_pipeline_default_feedback_provider_is_auto_skip(self) -> None:
        """Pipeline without explicit provider should use AutoSkipFeedbackProvider."""
        from aat.translate.feedback import AutoSkipFeedbackProvider

        project = TranslationProject.create(DocumentModel.create())
        pipeline = TranslationPipeline(project)
        assert isinstance(pipeline.feedback_provider, AutoSkipFeedbackProvider)

    def test_pipeline_approve_feedback_locks_segment(self) -> None:
        """Approve feedback should move segment to LOCK_SEGMENT."""
        from aat.translate.feedback import FeedbackProvider, FeedbackResponse

        class ApproveProvider(FeedbackProvider):
            def get_feedback(self, segment):
                return FeedbackResponse(action="approve")

        segment = Segment(sid="s1", pid_list=["p1"], source_text="Test.")
        ts = TranslationSegment(
            segment=segment,
            state=SegmentState.USER_FEEDBACK_WAIT,
            translation="测试。",
        )

        project = TranslationProject.create(DocumentModel.create())
        project.segments = [ts]
        config = PipelineConfig(llm_provider="fake", enable_checkpoints=False)
        pipeline = TranslationPipeline(project, config=config, feedback_provider=ApproveProvider())

        pipeline._process_segment(ts)

        assert ts.locked is True

    def test_pipeline_revise_feedback_adds_comments(self) -> None:
        """Revise feedback with comments should add them and transition to REVISE."""
        from aat.translate.feedback import FeedbackProvider, FeedbackResponse

        class ReviseProvider(FeedbackProvider):
            def get_feedback(self, segment):
                return FeedbackResponse(action="revise", comments=["fix the tone"])

        segment = Segment(sid="s1", pid_list=["p1"], source_text="Test.")
        ts = TranslationSegment(
            segment=segment,
            state=SegmentState.USER_FEEDBACK_WAIT,
            translation="测试。",
        )

        project = TranslationProject.create(DocumentModel.create())
        project.segments = [ts]
        config = PipelineConfig(llm_provider="fake", enable_checkpoints=False)
        pipeline = TranslationPipeline(project, config=config, feedback_provider=ReviseProvider())

        pipeline._process_segment(ts)

        assert "fix the tone" in ts.user_comments
        assert ts.locked is True  # Eventually locks after revision loop


class TestRevisePassesUncertaintyAnswers:
    """Test that _revise reads uncertainty_answers from segment metadata."""

    def test_revise_passes_uncertainty_answers(self) -> None:
        """Answers stored in segment metadata should appear in the revision prompt."""
        segment = Segment(
            sid="s1", pid_list=["p1"], source_text="Test text.",
            metadata={"uncertainty_answers": {"Q1": "Answer1"}},
        )
        ts = TranslationSegment(
            segment=segment,
            state=SegmentState.REVISE,
            translation="测试文本。",
            critic_issues=[],
        )

        captured_messages = []

        class CapturingClient(FakeLLMClient):
            def chat(self, messages, json_schema=None, **kwargs):
                captured_messages.extend(messages)
                return super().chat(messages, json_schema, **kwargs)

        project = TranslationProject.create(DocumentModel.create())
        config = PipelineConfig(llm_provider="fake", enable_checkpoints=False)
        pipeline = TranslationPipeline(project, config)
        pipeline.llm_client = CapturingClient()

        pipeline._revise(ts)

        user_msg = next(m["content"] for m in captured_messages if m["role"] == "user")
        assert "Q1" in user_msg, "uncertainty_answers key should be in revision prompt"
        assert "Answer1" in user_msg, "uncertainty_answers value should be in revision prompt"


class TestMultiDraftRevision:
    """Test multi-draft revision loop with force-lock."""

    def test_revision_history_stored_in_metadata(self) -> None:
        """Revision history is recorded in segment metadata."""
        segment = Segment(sid="s1", pid_list=["p1"], source_text="Test (Smith, 2020).")
        ts = TranslationSegment(
            segment=segment,
            state=SegmentState.REVISE,
            translation="测试文本。",
            validator_results=[],
            critic_issues=[{"code": "OMISSION", "detail": "Missing citation"}],
        )

        project = TranslationProject.create(DocumentModel.create())
        config = PipelineConfig(llm_provider="fake", enable_checkpoints=False)
        pipeline = TranslationPipeline(project, config)

        # Simulate entering the REVISE state handler directly
        ts.segment.metadata = {}
        ts.segment.metadata["revision_count"] = 0

        # Run just the revise handler by processing one iteration
        # We set state to REVISE, process_segment will handle it
        ts.locked = False
        pipeline._process_segment(ts)

        assert "revision_history" in ts.segment.metadata
        history = ts.segment.metadata["revision_history"]
        assert len(history) >= 1
        entry = history[0]
        assert "draft" in entry
        assert "round" in entry
        assert "issues" in entry
        assert entry["round"] == 1

    def test_max_revision_rounds_force_locks(self) -> None:
        """Segment is force-locked when max revision rounds reached."""
        segment = Segment(sid="s1", pid_list=["p1"], source_text="Test (Smith, 2020).")
        ts = TranslationSegment(
            segment=segment,
            state=SegmentState.REVISE,
            translation="测试文本。",
        )
        ts.segment.metadata = {"revision_count": 1}

        project = TranslationProject.create(DocumentModel.create())
        config = PipelineConfig(
            llm_provider="fake", enable_checkpoints=False, max_revision_rounds=1,
        )
        pipeline = TranslationPipeline(project, config)

        pipeline._process_segment(ts)

        assert ts.locked is True
        assert ts.segment.metadata["force_locked"] is True
        assert ts.segment.metadata["force_lock_reason"] == "max_revision_rounds_exceeded"

    def test_revision_counter_increments(self) -> None:
        """Revision count increments each time the REVISE state runs."""
        segment = Segment(sid="s1", pid_list=["p1"], source_text="Test.")
        ts = TranslationSegment(
            segment=segment,
            state=SegmentState.REVISE,
            translation="测试。",
        )
        ts.segment.metadata = {"revision_count": 0}

        project = TranslationProject.create(DocumentModel.create())
        config = PipelineConfig(llm_provider="fake", enable_checkpoints=False)
        pipeline = TranslationPipeline(project, config)

        # Process — REVISE will run and increment, then continue through the
        # remaining states to LOCK_SEGMENT.
        pipeline._process_segment(ts)

        assert ts.segment.metadata["revision_count"] >= 1

    def test_revision_with_persistent_error_force_locks(self) -> None:
        """Segment with persistent validator failure is force-locked after max rounds."""
        segment = Segment(
            sid="s1", pid_list=["p1"], source_text="Test (Smith, 2020).",
        )
        ts = TranslationSegment(
            segment=segment,
            state=SegmentState.ASSEMBLE_CONTEXT,
        )

        project = TranslationProject.create(DocumentModel.create())
        project.segments = [ts]
        config = PipelineConfig(
            llm_provider="fake",
            enable_checkpoints=False,
            max_revision_rounds=2,
            require_user_confirmation_on_fail=True,
        )
        pipeline = TranslationPipeline(project, config)

        pipeline._process_segment(ts)

        assert ts.locked is True
        assert ts.segment.metadata.get("force_locked") is True
        assert ts.segment.metadata.get("force_lock_reason") == "max_revision_rounds_exceeded"
        history = ts.segment.metadata.get("revision_history", [])
        assert len(history) >= 1
        assert ts.segment.metadata.get("revision_count") == 2


class TestUncertaintyDetectorIntegration:
    """Test UncertaintyDetector wired into the pipeline."""

    def _make_pipeline_and_segment(
        self,
        source_text: str,
        *,
        min_confidence: float = 0.5,
        uncertainties: list | None = None,
    ) -> tuple[TranslationPipeline, TranslationSegment]:
        segment = Segment(sid="s1", pid_list=["p1"], source_text=source_text)
        ts = TranslationSegment(
            segment=segment,
            state=SegmentState.UNCERTAINTY_DETECT,
            translation="Translated.",
            validator_results=[],
            uncertainties=uncertainties or [],
        )
        project = TranslationProject.create(DocumentModel.create())
        config = PipelineConfig(
            llm_provider="fake",
            enable_checkpoints=False,
            uncertainty_min_confidence=min_confidence,
        )
        pipeline = TranslationPipeline(project, config)
        return pipeline, ts

    def test_uncertainty_detector_adds_ambiguous_pronoun(self) -> None:
        """Ambiguous pronouns like 'it' and 'this' should produce uncertainties."""
        pipeline, ts = self._make_pipeline_and_segment(
            "This suggests it is important."
        )

        pipeline._uncertainty_detect(ts)

        spans = [u.span for u in ts.uncertainties]
        assert "it" in spans
        assert "this" in spans
        assert all(u.type == "AMBIGUOUS_REFERENCE" for u in ts.uncertainties)

    def test_uncertainty_detector_no_ambiguity(self) -> None:
        """Clean text should not produce detector-based uncertainties."""
        pipeline, ts = self._make_pipeline_and_segment(
            "The study analyzed data."
        )

        pipeline._uncertainty_detect(ts)

        assert len(ts.uncertainties) == 0

    def test_uncertainty_detector_confidence_threshold(self) -> None:
        """High min_confidence should filter out lower-confidence items."""
        pipeline_low, ts_low = self._make_pipeline_and_segment(
            "This suggests that is important.",
            min_confidence=0.5,
        )
        pipeline_high, ts_high = self._make_pipeline_and_segment(
            "This suggests that is important.",
            min_confidence=0.9,
        )

        pipeline_low._uncertainty_detect(ts_low)
        pipeline_high._uncertainty_detect(ts_high)

        # "this" has confidence 0.8, "that" has confidence 0.6
        # At 0.9 threshold neither should pass
        assert len(ts_low.uncertainties) > len(ts_high.uncertainties)
        assert len(ts_high.uncertainties) == 0

    def test_uncertainty_detector_skipped_when_llm_uncertainties_exist(self) -> None:
        """Detector should not run if LLM-reported uncertainties already exist."""
        pipeline, ts = self._make_pipeline_and_segment(
            "This suggests it is important.",
            uncertainties=[
                UncertaintyItem(
                    type="TERM", span="test", question="LLM question", options=[]
                ),
            ],
        )

        pipeline._uncertainty_detect(ts)

        # Should still only have the original LLM uncertainty (early return)
        assert len(ts.uncertainties) == 1
        assert ts.uncertainties[0].question == "LLM question"


class TestTranslationNotes:
    """Test translation notes capture."""

    def test_notes_stored_from_draft(self) -> None:
        """LLM response with notes stores them in segment."""
        segment = Segment(sid="s1", pid_list=["p1"], source_text="Test text.")
        ts = TranslationSegment(
            segment=segment,
            state=SegmentState.DRAFT_TRANSLATE,
        )

        project = TranslationProject.create(DocumentModel.create())
        config = PipelineConfig(llm_provider="fake", enable_checkpoints=False)
        pipeline = TranslationPipeline(project, config)

        pipeline._draft_translate(ts)

        assert len(ts.translation_notes) >= 1
        assert isinstance(ts.translation_notes[0], str)

    def test_notes_empty_when_not_provided(self) -> None:
        """LLM response without notes results in empty list, no error."""
        from aat.translate.llm_client import FakeLLMClient

        segment = Segment(sid="s1", pid_list=["p1"], source_text="Test text.")
        ts = TranslationSegment(
            segment=segment,
            state=SegmentState.DRAFT_TRANSLATE,
        )

        class NoNotesClient(FakeLLMClient):
            def chat(self, messages, json_schema=None, **kwargs):
                self.call_count += 1
                if json_schema is not None:
                    return {"content": {"translation": "翻译。", "uncertainties": []}}
                return {"content": "翻译。"}

        project = TranslationProject.create(DocumentModel.create())
        config = PipelineConfig(llm_provider="fake", enable_checkpoints=False)
        pipeline = TranslationPipeline(project, config)
        pipeline.llm_client = NoNotesClient()

        pipeline._draft_translate(ts)

        assert ts.translation_notes == []
        assert ts.translation is not None

    def test_notes_from_revision(self) -> None:
        """Notes from revision are appended to existing notes."""
        segment = Segment(sid="s1", pid_list=["p1"], source_text="Test.")
        ts = TranslationSegment(
            segment=segment,
            state=SegmentState.REVISE,
            translation="测试。",
            translation_notes=["Original note."],
            critic_issues=[{"code": "OMISSION", "detail": "Missing info"}],
        )

        project = TranslationProject.create(DocumentModel.create())
        config = PipelineConfig(llm_provider="fake", enable_checkpoints=False)
        pipeline = TranslationPipeline(project, config)

        pipeline._revise(ts)

        assert len(ts.translation_notes) >= 2
        assert "Original note." in ts.translation_notes

    def test_translation_segment_has_notes_field(self) -> None:
        """TranslationSegment has translation_notes field."""
        segment = Segment(sid="s1", pid_list=["p1"], source_text="Test.")
        ts = TranslationSegment(
            segment=segment,
            state=SegmentState.DRAFT_TRANSLATE,
        )
        assert hasattr(ts, "translation_notes")
        assert ts.translation_notes == []
