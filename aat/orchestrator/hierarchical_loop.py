"""Hierarchical Translation Loop for segment-by-segment translation."""

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Callable

# Runtime imports for type hints
if TYPE_CHECKING:
    from aat.storage.models import (
        TranslationSegment,
        TranslationProject,
        ValidationResult,
        SegmentState,
    )

# Imports needed at runtime for tests
from aat.storage.models import (
    ValidationResult,
    SegmentState,
)
from aat.orchestrator.context_assembler import (
    ContextAssembler,
    ContextConfig,
    AssembledContext,
)
from aat.storage.checkpoints import CheckpointManager, Checkpoint


@dataclass
class TranslationResult:
    """Result of translating a segment."""

    segment_id: str
    success: bool
    translation: str | None = None
    validation_results: list[ValidationResult] = field(default_factory=list)
    validator_issues: list[dict] = field(default_factory=list)
    critic_issues: list[dict] = field(default_factory=list)
    uncertainties: list[dict] = field(default_factory=list)
    locked: bool = False
    error_message: str | None = None


@dataclass
class LoopState:
    """State of the hierarchical translation loop."""

    project_id: str
    current_segment_index: int = 0
    total_segments: int = 0
    completed_count: int = 0
    failed_count: int = 0
    current_chapter: str | None = None


class HierarchicalTranslator:
    """Hierarchical translator for segment-by-segment translation."""

    def __init__(
        self,
        project_dir: Path,
        checkpoint_manager: CheckpointManager,
        context_assembler: ContextAssembler | None = None,
        llm_client: Callable | None = None,
        validators: list[Callable] | None = None,
        on_segment_complete: Callable[[TranslationResult], None] | None = None,
        on_error: Callable[[Exception], None] | None = None,
    ) -> None:
        """
        Initialize hierarchical translator.

        Args:
            project_dir: Project directory path.
            checkpoint_manager: CheckpointManager instance.
            context_assembler: Optional ContextAssembler.
            llm_client: Optional LLM client for translation.
            validators: Optional list of validator functions.
            on_segment_complete: Callback when segment completes.
            on_error: Callback on errors.
        """
        self.project_dir = Path(project_dir)
        self.checkpoint_manager = checkpoint_manager
        self.context_assembler = context_assembler
        self.llm_client = llm_client
        self.validators = validators or []
        self.on_segment_complete = on_segment_complete
        self.on_error = on_error

    def translate_segment(
        self,
        segment: "TranslationSegment",
        termbank: dict | None = None,
        previous_translation: str | None = None,
        chapter_summary: dict | None = None,
        global_style: dict | None = None,
    ) -> TranslationResult:
        """
        Translate a single segment with hierarchical context.

        Args:
            segment: TranslationSegment to translate.
            termbank: Translation memory with locked entries.
            previous_translation: Previous segment's translation.
            chapter_summary: Summary of previous chapter.
            global_style: Global style guide.

        Returns:
            TranslationResult with translation and validation results.
        """
        # Get segment_id safely, handling None cases
        try:
            segment_id = segment.segment.sid if segment.segment else "unknown"
        except AttributeError:
            segment_id = "unknown"

        try:
            # Assemble hierarchical context if assembler available
            context = None
            if self.context_assembler:
                context = self.context_assembler.assemble_context_for_segment(
                    segment_id=segment_id,
                    chapter_id=segment.metadata.get("chapter_id") if hasattr(segment, "metadata") else None,
                    termbank=termbank,
                    previous_translation=previous_translation,
                    chapter_summary=chapter_summary,
                    global_style=global_style,
                )

            # Translate using LLM if client available
            translation = None
            if self.llm_client and context:
                # In production, this would call the LLM
                # For now, we use a placeholder
                translation = self._mock_translation(
                    segment.segment.source_text,
                    context.context_text if context else "",
                )

            # If no translation provided, use source text as fallback
            if not translation:
                translation = segment.segment.source_text

            # Run validators
            validation_results = []
            validator_issues = []

            for validator in self.validators:
                try:
                    result = validator(segment.segment.source_text, translation)
                    if result:
                        validation_results.append(result)
                        if result.issues:
                            for issue in result.issues:
                                validator_issues.append({
                                    "code": issue.code,
                                    "detail": issue.detail,
                                })
                except Exception as e:
                    validator_issues.append({
                        "code": "VALIDATOR_ERROR",
                        "detail": str(e),
                    })

            # Check if translation passes validation
            is_valid = all(
                not result.is_fail() for result in validation_results
            )
            locked = is_valid

            result = TranslationResult(
                segment_id=segment_id,
                success=True,
                translation=translation,
                validation_results=validation_results,
                validator_issues=validator_issues,
                locked=locked,
            )

            # Notify callback
            if self.on_segment_complete:
                self.on_segment_complete(result)

            return result

        except Exception as e:
            error_msg = f"Error translating segment {segment_id}: {str(e)}"

            # Notify error callback
            if self.on_error:
                self.on_error(e)

            return TranslationResult(
                segment_id=segment_id,
                success=False,
                error_message=error_msg,
            )

    def _mock_translation(
        self,
        source_text: str,
        context: str,
    ) -> str:
        """
        Mock translation for testing purposes.

        In production, this would be replaced with actual LLM call.

        Args:
            source_text: Source text to translate.
            context: Hierarchical context.

        Returns:
            Mock translation.
        """
        # Simple mock: prepend context marker and use source
        return f"[翻译] {source_text}"

    def process_segments(
        self,
        project: "TranslationProject",
        max_tokens: int = 4000,
    ) -> dict:
        """
        Process all segments in a project.

        Args:
            project: TranslationProject to process.
            max_tokens: Maximum tokens per context.

        Returns:
            Dictionary with processing statistics.
        """
        loop_state = LoopState(
            project_id=project.project_id,
            total_segments=len(project.segments),
        )

        results = []
        current_chapter = None
        previous_translation = None
        chapter_segments = []

        for i, segment in enumerate(project.segments):
            loop_state.current_segment_index = i

            # Skip locked segments (already completed)
            if segment.locked:
                loop_state.completed_count += 1
                if segment.translation:
                    previous_translation = segment.translation
                continue

            # Check chapter change
            segment_chapter = (
                segment.metadata.get("chapter_id")
                if hasattr(segment, "metadata")
                else None
            )

            if segment_chapter != current_chapter:
                # Generate chapter summary for previous chapter
                if current_chapter and chapter_segments:
                    # In production, generate and save summary
                    pass

                current_chapter = segment_chapter
                chapter_segments = []

            chapter_segments.append(segment)

            # Translate segment
            result = self.translate_segment(
                segment,
                termbank=None,  # In production, pass actual TM
                previous_translation=previous_translation,
                chapter_summary=None,  # In production, load from storage
                global_style=None,  # In production, load from storage
            )

            results.append(result)

            if result.success:
                if result.locked:
                    loop_state.completed_count += 1
                    # Update segment with translation
                    segment.translation = result.translation
                    segment.locked = True
                    previous_translation = result.translation
                else:
                    loop_state.failed_count += 1
            else:
                loop_state.failed_count += 1

            # Save checkpoint periodically
            if (i + 1) % 5 == 0:  # Every 5 segments
                self._save_checkpoint(project, loop_state)

        # Save final checkpoint
        self._save_checkpoint(project, loop_state)

        return {
            "project_id": loop_state.project_id,
            "total_segments": loop_state.total_segments,
            "completed_count": loop_state.completed_count,
            "failed_count": loop_state.failed_count,
            "results": [r.to_dict() if hasattr(r, "to_dict") else self._result_to_dict(r) for r in results],
        }

    def _save_checkpoint(
        self,
        project: "TranslationProject",
        loop_state: LoopState,
    ) -> None:
        """
        Save checkpoint for current state.

        Args:
            project: TranslationProject.
            loop_state: Current loop state.
        """
        checkpoint = Checkpoint(
            project_id=project.project_id,
            timestamp=datetime.now().isoformat(),
            segment_states={
                seg.segment.sid: {
                    "sid": seg.segment.sid,
                    "source_text": seg.segment.source_text,
                    "translation": seg.translation,
                    "state": seg.state.value,
                    "locked": seg.locked,
                }
                for seg in project.segments
            },
            metadata={
                "title": project.document.title,
                "total_segments": loop_state.total_segments,
                "completed_segments": loop_state.completed_count,
                "current_index": loop_state.current_segment_index,
            },
        )

        self.checkpoint_manager.save_checkpoint(checkpoint)

    def _result_to_dict(self, result: TranslationResult) -> dict:
        """Convert TranslationResult to dictionary."""
        return {
            "segment_id": result.segment_id,
            "success": result.success,
            "translation": result.translation,
            "validator_issues": result.validator_issues,
            "critic_issues": result.critic_issues,
            "uncertainties": result.uncertainties,
            "locked": result.locked,
            "error_message": result.error_message,
        }


def estimate_token_count(text: str) -> int:
    """
    Estimate token count for text.

    Args:
        text: Text to estimate.

    Returns:
        Estimated token count (~4 chars per token).
    """
    if not text:
        return 0
    return len(text) // 4


def validate_context_size(text: str, max_tokens: int) -> tuple[bool, int]:
    """
    Validate context size against token budget.

    Args:
        text: Context text to validate.
        max_tokens: Maximum allowed tokens.

    Returns:
        Tuple of (is_valid, actual_token_count).
    """
    token_count = estimate_token_count(text)
    is_valid = token_count <= max_tokens
    return is_valid, token_count
