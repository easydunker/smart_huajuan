"""Integration tests for Hierarchical Translation Loop."""

from typing import TYPE_CHECKING
import tempfile
from pathlib import Path

import pytest

# Local imports for type hints
if TYPE_CHECKING:
    from aat.orchestrator.hierarchical_loop import (
        HierarchicalTranslator,
        TranslationResult,
        LoopState,
    )
else:
    from aat.orchestrator.hierarchical_loop import (
        HierarchicalTranslator,
        TranslationResult,
        LoopState,
    )

from aat.orchestrator.hierarchical_loop import (
    estimate_token_count,
    validate_context_size,
)


class TestTranslationResult:
    "Test TranslationResult dataclass."

    def test_creation(self) -> None:
        "Test creating translation result."
        result = TranslationResult(
            segment_id="s1",
            success=True,
            translation="Test translation",
            locked=True,
        )

        assert result.segment_id == "s1"
        assert result.success is True
        assert result.translation == "Test translation"
        assert result.locked is True

    def test_failed_result(self) -> None:
        "Test failed translation result."
        result = TranslationResult(
            segment_id="s1",
            success=False,
            error_message="Translation failed.",
        )

        assert result.success is False
        assert result.error_message == "Translation failed."

    def test_with_validation_issues(self) -> None:
        "Test result with validation issues."
        result = TranslationResult(
            segment_id="s1",
            success=True,
            translation="Translation",
            validator_issues=[
                {"code": "CITATION_ERROR", "detail": "Citation mismatch"},
            ],
            locked=False,  # Failed validation
        )

        assert len(result.validator_issues) == 1
        assert result.locked is False


class TestLoopState:
    "Test LoopState dataclass."

    def test_creation(self) -> None:
        "Test creating loop state."
        state = LoopState(
            project_id="test-project",
            total_segments=10,
            current_segment_index=5,
            completed_count=3,
            failed_count=1,
            current_chapter="ch1",
        )

        assert state.project_id == "test-project"
        assert state.total_segments == 10
        assert state.completed_count == 3
        assert state.failed_count == 1

    def test_defaults(self) -> None:
        "Test default loop state values."
        state = LoopState(project_id="test-project")

        assert state.current_segment_index == 0
        assert state.total_segments == 0
        assert state.completed_count == 0
        assert state.failed_count == 0
        assert state.current_chapter is None


class TestEstimateTokenCount:
    "Test token count estimation."

    def test_empty_text(self) -> None:
        "Test token count for empty text."
        assert estimate_token_count("") == 0
        assert estimate_token_count(None) == 0

    def test_short_text(self) -> None:
        "Test token count for short text."
        # 5 chars // 4 = 1 token
        assert estimate_token_count("hello") == 1

    def test_longer_text(self) -> None:
        "Test token count for longer text."
        # 20 chars // 4 = 5 tokens
        text = "hello world test code"
        assert estimate_token_count(text) == 5


class TestValidateContextSize:
    "Test context size validation."

    def test_within_budget(self) -> None:
        "Test validation within token budget."
        text = "Short context."
        is_valid, token_count = validate_context_size(text, max_tokens=1000)

        assert is_valid is True
        assert token_count <= 1000

    def test_over_budget(self) -> None:
        "Test validation over token budget."
        text = "This is a very long context. " * 500

        # Should be over budget
        is_valid, token_count = validate_context_size(text, max_tokens=100)

        assert is_valid is False
        assert token_count > 100

    def test_empty_context(self) -> None:
        "Test validation of empty context."
        is_valid, token_count = validate_context_size("", max_tokens=1000)

        assert is_valid is True
        assert token_count == 0


class TestHierarchicalTranslator:
    "Test HierarchicalTranslator functionality."

    @pytest.fixture
    def temp_dir(self) -> Path:
        "Create temporary directory."
        return Path(tempfile.mkdtemp())

    def test_init(self, temp_dir: Path) -> None:
        "Test initialization."
        from aat.storage.checkpoints import CheckpointManager

        checkpoint_manager = CheckpointManager(temp_dir)
        translator = HierarchicalTranslator(
            project_dir=temp_dir,
            checkpoint_manager=checkpoint_manager,
        )

        assert translator.project_dir == temp_dir
        assert translator.checkpoint_manager == checkpoint_manager

    def test_translate_segment_with_mock(
        self, temp_dir: Path
    ) -> None:
        "Test translating segment with mock translation."
        from aat.storage.checkpoints import CheckpointManager
        from aat.storage.models import TranslationSegment, Segment, SegmentState

        checkpoint_manager = CheckpointManager(temp_dir)
        translator = HierarchicalTranslator(
            project_dir=temp_dir,
            checkpoint_manager=checkpoint_manager,
        )

        segment = TranslationSegment(
            segment=Segment(sid="s1", pid_list=["p1"], source_text="Test segment."),
            state=SegmentState.DRAFT_TRANSLATE,
        )

        result = translator.translate_segment(segment)

        assert result.segment_id == "s1"
        assert result.success is True
        assert result.translation is not None

    def test_translate_segment_with_context(
        self, temp_dir: Path
    ) -> None:
        "Test translating segment with hierarchical context."
        from aat.storage.checkpoints import CheckpointManager
        from aat.storage.models import TranslationSegment, Segment, SegmentState
        from aat.orchestrator.context_assembler import ContextAssembler

        checkpoint_manager = CheckpointManager(temp_dir)
        context_assembler = ContextAssembler(temp_dir)

        translator = HierarchicalTranslator(
            project_dir=temp_dir,
            checkpoint_manager=checkpoint_manager,
            context_assembler=context_assembler,
        )

        segment = TranslationSegment(
            segment=Segment(sid="s1", pid_list=["p1"], source_text="Test segment."),
            state=SegmentState.DRAFT_TRANSLATE,
        )

        result = translator.translate_segment(
            segment,
            termbank=None,
            previous_translation="Previous translation.",
            chapter_summary=None,
            global_style=None,
        )

        assert result.segment_id == "s1"
        assert result.success is True

    def test_translate_segment_with_validators(
        self, temp_dir: Path
    ) -> None:
        "Test translating segment with validators."
        from aat.storage.checkpoints import CheckpointManager
        from aat.storage.models import (
            TranslationSegment,
            Segment,
            SegmentState,
            ValidationResult,
            ValidatorStatus,
        )

        checkpoint_manager = CheckpointManager(temp_dir)
        translator = HierarchicalTranslator(
            project_dir=temp_dir,
            checkpoint_manager=checkpoint_manager,
        )

        # Create a validator that always passes
        def passing_validator(source: str, translation: str) -> ValidationResult:
            return ValidationResult(status=ValidatorStatus.PASS)

        translator.validators = [passing_validator]

        segment = TranslationSegment(
            segment=Segment(sid="s1", pid_list=["p1"], source_text="Test."),
            state=SegmentState.DRAFT_TRANSLATE,
        )

        result = translator.translate_segment(segment)

        assert result.success is True
        assert result.locked is True  # Should be locked if validation passes

    def test_translate_segment_with_failing_validator(
        self, temp_dir: Path
    ) -> None:
        "Test translating segment with failing validator."
        from aat.storage.checkpoints import CheckpointManager
        from aat.storage.models import (
            TranslationSegment,
            Segment,
            SegmentState,
            ValidationResult,
            ValidatorStatus,
            ValidatorIssue,
        )

        checkpoint_manager = CheckpointManager(temp_dir)
        translator = HierarchicalTranslator(
            project_dir=temp_dir,
            checkpoint_manager=checkpoint_manager,
        )

        # Create a validator that fails
        def failing_validator(source: str, translation: str) -> ValidationResult:
            return ValidationResult(
                status=ValidatorStatus.FAIL,
                issues=[ValidatorIssue(code="TEST_FAIL", detail="Test failure")],
            )

        translator.validators = [failing_validator]

        segment = TranslationSegment(
            segment=Segment(sid="s1", pid_list=["p1"], source_text="Test."),
            state=SegmentState.DRAFT_TRANSLATE,
        )

        result = translator.translate_segment(segment)

        assert result.success is True  # Translation succeeded
        assert result.locked is False  # Should NOT be locked if validation fails
        assert len(result.validator_issues) > 0

    def test_callback_on_segment_complete(
        self, temp_dir: Path
    ) -> None:
        "Test callback when segment completes."
        from aat.storage.checkpoints import CheckpointManager
        from aat.storage.models import TranslationSegment, Segment, SegmentState

        checkpoint_manager = CheckpointManager(temp_dir)

        completed_results = []

        def on_complete(result: TranslationResult) -> None:
            completed_results.append(result)

        translator = HierarchicalTranslator(
            project_dir=temp_dir,
            checkpoint_manager=checkpoint_manager,
            on_segment_complete=on_complete,
        )

        segment = TranslationSegment(
            segment=Segment(sid="s1", pid_list=["p1"], source_text="Test."),
            state=SegmentState.DRAFT_TRANSLATE,
        )

        translator.translate_segment(segment)

        assert len(completed_results) == 1
        assert completed_results[0].segment_id == "s1"

    def test_no_full_document_prompt_verification(
        self, temp_dir: Path
    ) -> None:
        "Verify no full-document prompt exists in code."
        from aat.orchestrator.hierarchical_loop import HierarchicalTranslator

        # Check class methods
        methods = [name for name in dir(HierarchicalTranslator) if not name.startswith("_")]
        assert "process_segments" in methods  # Method exists for per-segment processing
        assert "translate_segment" in methods  # Method exists for per-segment translation
        # Verify no method named like "translate_document" or "process_full_document"
        assert "translate_document" not in methods
        assert "process_full_document" not in methods

    def test_translate_segment_with_callback_results(
        self, temp_dir: Path
    ) -> None:
        "Test translate_segment returns correct results."
        from aat.storage.checkpoints import CheckpointManager
        from aat.storage.models import TranslationSegment, Segment, SegmentState

        checkpoint_manager = CheckpointManager(temp_dir)
        translator = HierarchicalTranslator(
            project_dir=temp_dir,
            checkpoint_manager=checkpoint_manager,
        )

        # Create mock validator
        def mock_validator(source: str, translation: str):
            return None  # Always pass

        translator.validators = [mock_validator]

        segment = TranslationSegment(
            segment=Segment(sid="s1", pid_list=["p1"], source_text="Test segment."),
            state=SegmentState.DRAFT_TRANSLATE,
        )

        result = translator.translate_segment(segment)

        assert result.segment_id == "s1"
        assert result.success is True
        assert result.translation is not None
        assert result.locked is True  # Should be locked when validation passes

    def test_translate_segment_without_validators(
        self, temp_dir: Path
    ) -> None:
        "Test translate_segment without validators locks by default."
        from aat.storage.checkpoints import CheckpointManager
        from aat.storage.models import TranslationSegment, Segment, SegmentState

        checkpoint_manager = CheckpointManager(temp_dir)
        translator = HierarchicalTranslator(
            project_dir=temp_dir,
            checkpoint_manager=checkpoint_manager,
        )

        segment = TranslationSegment(
            segment=Segment(sid="s1", pid_list=["p1"], source_text="Test segment."),
            state=SegmentState.DRAFT_TRANSLATE,
        )

        result = translator.translate_segment(segment)

        # Should be locked even without explicit validators
        # (default behavior when no validators = provided)
        assert result.success is True
        assert result.translation is not None
        assert result.locked is True

    def test_translate_segment_error_handling(
        self, temp_dir: Path
    ) -> None:
        "Test translate_segment error handling."
        from aat.storage.checkpoints import CheckpointManager
        from aat.storage.models import TranslationSegment, Segment, SegmentState

        # Create a mock segment that will cause an error
        class BrokenSegment:
            pass

        checkpoint_manager = CheckpointManager(temp_dir)
        translator = HierarchicalTranslator(
            project_dir=temp_dir,
            checkpoint_manager=checkpoint_manager,
        )

        # This will cause an error because segment.segment won't exist
        broken_segment = BrokenSegment()
        broken_segment.segment = None  # Will cause error
        broken_segment.state = SegmentState.DRAFT_TRANSLATE

        result = translator.translate_segment(broken_segment)

        # Should fail gracefully
        assert result.success is False
        assert result.error_message is not None
