"""Translation pipeline for processing segments through state machine."""

import json
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

from aat.storage.checkpoints import Checkpoint, CheckpointManager
from aat.storage.models import (
    DraftTranslationResult,
    Segment,
    SegmentState,
    SegmenterError,
    TranslationProject,
    TranslationSegment,
    UncertaintyItem,
    ValidatorIssue,
    ValidatorStatus,
)
from aat.translate.llm_client import LLMClient, LLMError, create_client
from aat.translate.prompts import (
    CriticReviewPrompt,
    DraftTranslationPrompt,
    PlanningPrompt,
    RevisionPrompt,
)
from aat.translate.translation_memory import TranslationMemory, TMEntry
from aat.translate.quality import run_quality_heuristics
from aat.translate.validators import (
    CitationPreservationValidator,
    LengthChangeHeuristic,
    NumericFidelityValidator,
    ReferenceInjectionValidator,
    UncertaintyDetector,
    has_any_failures,
    has_any_flags,
    run_all_validators,
)
from aat.orchestrator.context_assembler import ContextAssembler, ContextConfig

if TYPE_CHECKING:
    pass


class PipelineError(Exception):
    """Exception raised for pipeline errors."""


@dataclass
class PipelineConfig:
    """Configuration for translation pipeline."""

    # LLM configuration
    llm_provider: str = "anthropic"  # "anthropic", "ollama", "openai", or "fake"
    llm_model: str = "claude-3-5-sonnet-20241022"
    llm_api_key: str | None = None  # For OpenAI
    llm_host: str = "http://localhost:11434"  # For Ollama

    # Validator configuration
    require_user_confirmation_on_fail: bool = True
    require_user_confirmation_on_flag: bool = False

    # Uncertainty detection
    uncertainty_min_confidence: float = 0.5

    # Revision loop
    max_revision_rounds: int = 2

    # Quality heuristics
    enable_quality_heuristics: bool = True

    # Checkpoint configuration
    enable_checkpoints: bool = True
    checkpoint_interval: int = 1  # Save after every N segments


class TranslationPipeline:
    """Pipeline for translating segments through state machine."""

    def __init__(
        self,
        project: TranslationProject,
        config: PipelineConfig | None = None,
        feedback_provider: "FeedbackProvider | None" = None,
    ) -> None:
        """
        Initialize translation pipeline.

        Args:
            project: Translation project with document and segments.
            config: Pipeline configuration.
            feedback_provider: Provider for human feedback at USER_FEEDBACK_WAIT.
        """
        self.project = project
        self.config = config or PipelineConfig()

        from aat.translate.feedback import AutoSkipFeedbackProvider, FeedbackProvider
        self.feedback_provider: FeedbackProvider = feedback_provider or AutoSkipFeedbackProvider()

        # Initialize components
        self.llm_client = create_client(
            provider=self.config.llm_provider,
            model=self.config.llm_model,
            api_key=self.config.llm_api_key,
            host=self.config.llm_host,
        )

        # Initialize validators
        self.validators = run_all_validators

        # Initialize translation memory
        self.translation_memory = TranslationMemory(project_id=project.project_id)

        # Initialize context assembler
        self.context_assembler = ContextAssembler(
            project_dir=Path.cwd(),
            config=ContextConfig(
                include_global_style=False,
                include_chapter_summary=False,
            ),
        )

        # Initialize checkpoint manager
        if self.config.enable_checkpoints:
            self.checkpoint_manager = CheckpointManager(Path.cwd())
        else:
            self.checkpoint_manager = None

    def run(self) -> TranslationProject:
        """
        Run the full translation pipeline.

        Returns:
            Updated TranslationProject with all segments processed.

        Raises:
            PipelineError: If pipeline fails.
        """
        # Create segments from document if not already created
        if not self.project.segments:
            self._create_segments_from_document()

        # Process each segment through state machine
        total_segments = len(self.project.segments)
        print(f"\n🚀 Starting translation of {total_segments} segments...", file=sys.stderr, flush=True)

        for i, translation_segment in enumerate(self.project.segments):
            print(f"\n📄 Segment {i+1}/{total_segments}", file=sys.stderr, flush=True)
            self._process_segment(translation_segment, segment_index=i+1, total_segments=total_segments)

            # Progress update
            if (i + 1) % 10 == 0 or i == total_segments - 1:
                percent = (i + 1) / total_segments * 100
                print(f"\n📊 Progress: {i+1}/{total_segments} segments ({percent:.1f}%)", file=sys.stderr, flush=True)

            # Save checkpoint periodically
            if (
                self.config.enable_checkpoints
                and self.checkpoint_manager
                and (i + 1) % self.config.checkpoint_interval == 0
            ):
                print(f"💾 Saving checkpoint...", file=sys.stderr, flush=True)
                self._save_checkpoint()
                print(f"✓ Checkpoint saved", file=sys.stderr, flush=True)

        # Save final checkpoint
        if self.config.enable_checkpoints and self.checkpoint_manager:
            self._save_checkpoint()

        return self.project

    def _process_segment(self, segment: TranslationSegment, segment_index: int = 0, total_segments: int = 0) -> None:
        """
        Process a single segment through state machine.

        Args:
            segment: TranslationSegment to process.
            segment_index: Index of current segment for progress tracking.
            total_segments: Total number of segments for progress tracking.
        """
        import time

        state_start_time = time.time()
        state_count = 0
        max_iterations = 100  # Prevent infinite loops

        while not segment.locked:
            state_count += 1

            # Safety check: prevent infinite loops
            if state_count > max_iterations:
                print(f"   ⚠️ Max iterations ({max_iterations}) reached for segment {segment_index}. Locking segment.", file=sys.stderr, flush=True)
                segment.locked = True
                break

            current_state = segment.state.name

            # Log every state transition (for debugging stuck processes)
            if state_count % 10 == 0 or state_count == 1:
                elapsed = time.time() - state_start_time
                print(f"   ⏳ Segment {segment_index}: state {current_state} (iteration {state_count}, {elapsed:.1f}s)",
                      file=sys.stderr, flush=True)

            # Execute state machine transition
            # Use .name for comparison since SegmentState is a str, Enum
            if segment.state.name == "ASSEMBLE_CONTEXT":
                print(f"   📥 ASSEMBLE_CONTEXT...", file=sys.stderr, flush=True)
                self._assemble_context(segment)
                segment.state = SegmentState.PLANNING
                print(f"   ✓ ASSEMBLE_CONTEXT done", file=sys.stderr, flush=True)
            elif segment.state.name == "PLANNING":
                print(f"   📋 PLANNING...", file=sys.stderr, flush=True)
                self._planning_analysis(segment)
                segment.state = SegmentState.DRAFT_TRANSLATE
                print(f"   ✓ PLANNING done", file=sys.stderr, flush=True)
            elif segment.state.name == "DRAFT_TRANSLATE":
                print(f"   🌐 DRAFT_TRANSLATE...", file=sys.stderr, flush=True)
                self._draft_translate(segment, segment_index=segment_index, total_segments=total_segments)
                segment.state = SegmentState.DETERMINISTIC_VALIDATE
                print(f"   ✓ DRAFT_TRANSLATE done", file=sys.stderr, flush=True)
            elif segment.state.name == "DETERMINISTIC_VALIDATE":
                print(f"   ✓ DETERMINISTIC_VALIDATE...", file=sys.stderr, flush=True)
                self._deterministic_validate(segment)
                if self._should_block_on_validator_results(segment):
                    segment.state = SegmentState.USER_FEEDBACK_WAIT
                else:
                    segment.state = SegmentState.LLM_CRITIC_REVIEW
                print(f"   ✓ DETERMINISTIC_VALIDATE done", file=sys.stderr, flush=True)
            elif segment.state.name == "LLM_CRITIC_REVIEW":
                print(f"   🔍 LLM_CRITIC_REVIEW...", file=sys.stderr, flush=True)
                self._llm_critic_review(segment)
                # Run advisory quality heuristics after critic review
                if self.config.enable_quality_heuristics and segment.translation:
                    self._run_quality_heuristics(segment)
                segment.state = SegmentState.UNCERTAINTY_DETECT
                print(f"   ✓ LLM_CRITIC_REVIEW done", file=sys.stderr, flush=True)
            elif segment.state.name == "UNCERTAINTY_DETECT":
                print(f"   ❓ UNCERTAINTY_DETECT...", file=sys.stderr, flush=True)
                self._uncertainty_detect(segment)
                if self._has_uncertainties(segment):
                    segment.state = SegmentState.USER_FEEDBACK_WAIT
                else:
                    segment.state = SegmentState.LOCK_SEGMENT
                print(f"   ✓ UNCERTAINTY_DETECT done", file=sys.stderr, flush=True)
            elif segment.state.name == "USER_FEEDBACK_WAIT":
                print(f"   👤 USER_FEEDBACK_WAIT...", file=sys.stderr, flush=True)
                response = self.feedback_provider.get_feedback(segment)
                if response.action == "approve":
                    segment.state = SegmentState.LOCK_SEGMENT
                elif response.action == "revise":
                    segment.user_comments.extend(response.comments)
                    segment.structured_feedback.extend(response.structured_feedback)
                    if response.answers:
                        if not segment.segment.metadata:
                            segment.segment.metadata = {}
                        existing = segment.segment.metadata.get("uncertainty_answers", {})
                        existing.update(response.answers)
                        segment.segment.metadata["uncertainty_answers"] = existing
                    segment.state = SegmentState.REVISE
                else:
                    segment.state = SegmentState.REVISE
            elif segment.state.name == "REVISE":
                if not segment.segment.metadata:
                    segment.segment.metadata = {}
                revision_count = segment.segment.metadata.get("revision_count", 0)

                if revision_count >= self.config.max_revision_rounds:
                    print(f"   ⚠️ Max revision rounds ({self.config.max_revision_rounds}) reached. Force-locking segment.", file=sys.stderr, flush=True)
                    segment.segment.metadata["force_locked"] = True
                    segment.segment.metadata["force_lock_reason"] = "max_revision_rounds_exceeded"
                    segment.locked = True
                    continue

                if "revision_history" not in segment.segment.metadata:
                    segment.segment.metadata["revision_history"] = []

                current_issues: list[dict] = []
                for result in segment.validator_results:
                    if result.is_fail():
                        for issue in result.issues:
                            current_issues.append({"code": issue.code, "detail": issue.detail})
                current_issues.extend(segment.critic_issues)

                segment.segment.metadata["revision_history"].append({
                    "draft": segment.translation or "",
                    "round": revision_count + 1,
                    "issues": current_issues,
                })

                print(f"   📝 REVISE (round {revision_count + 1}/{self.config.max_revision_rounds})...", file=sys.stderr, flush=True)
                self._revise(segment)
                segment.segment.metadata["revision_count"] = revision_count + 1
                segment.state = SegmentState.DETERMINISTIC_VALIDATE
                print(f"   ✓ REVISE done", file=sys.stderr, flush=True)
            elif segment.state.name == "LOCK_SEGMENT":
                # Segment is complete
                print(f"   🔒 LOCK_SEGMENT (complete)", file=sys.stderr, flush=True)
                segment.locked = True
            else:
                raise PipelineError(f"Unknown state: {segment.state}")

        total_time = time.time() - state_start_time
        print(f"   ✅ Segment {segment_index} complete in {total_time:.1f}s ({state_count} state transitions)", file=sys.stderr, flush=True)

    def _assemble_context(self, segment: TranslationSegment) -> None:
        """
        Assemble hierarchical context for translation using ContextAssembler.

        Gathers previous segment translation and locked terminology,
        then stores the assembled context in the segment's metadata.

        Args:
            segment: TranslationSegment to process.
        """
        previous_translation = self._get_previous_translation(segment)

        locked_terms = self.translation_memory.get_locked_terms()
        termbank_dict = None
        if locked_terms:
            termbank_dict = {
                "locked": [
                    {"source_phrase": e.source_phrase, "target_phrase": e.target_phrase}
                    for e in locked_terms
                ]
            }

        assembled = self.context_assembler.assemble_context_for_segment(
            segment_id=segment.segment.sid,
            chapter_id=getattr(segment.segment, "chapter_id", None),
            termbank=termbank_dict,
            previous_translation=previous_translation,
        )

        if not segment.segment.metadata:
            segment.segment.metadata = {}
        segment.segment.metadata["assembled_context"] = assembled.context_text
        segment.segment.metadata["context_token_count"] = assembled.token_count

    def _get_previous_translation(self, segment: TranslationSegment) -> str | None:
        """Get the translation of the segment immediately before this one."""
        segments = self.project.segments
        for i, seg in enumerate(segments):
            if seg.segment.sid == segment.segment.sid and i > 0:
                prev = segments[i - 1]
                if prev.translation:
                    return prev.translation
                break
        return None

    def _planning_analysis(self, segment: TranslationSegment) -> None:
        """
        Perform pre-translation planning analysis.

        Analyzes the segment to identify:
        - Segment type (title, abstract, introduction, etc.)
        - Key terminology
        - Special formats (citations, numbers, formulas)
        - Translation strategy

        Args:
            segment: TranslationSegment to analyze.
        """
        try:
            # Build planning prompt
            messages = PlanningPrompt.build(
                source_text=segment.segment.source_text,
                context_before=segment.segment.context_before,
                context_after=segment.segment.context_after,
            )

            # Get schema
            schema = PlanningPrompt.get_response_schema()

            # Call LLM for planning analysis
            response = self.llm_client.chat(
                messages=messages,
                json_schema=schema,
                temperature=0.2,  # Lower temperature for more consistent analysis
            )

            # Parse and store planning analysis in segment metadata
            content = response.get("content", {})
            if isinstance(content, dict):
                # Store planning analysis in segment metadata
                if not segment.segment.metadata:
                    segment.segment.metadata = {}
                segment.segment.metadata["planning_analysis"] = {
                    "segment_type": content.get("segment_type", "其他"),
                    "key_terms": content.get("key_terms", []),
                    "special_formats": content.get("special_formats", []),
                    "translation_strategy": content.get("translation_strategy", ""),
                }

                # Extract and lock key terms into translation memory
                self._extract_and_lock_terms(content.get("key_terms", []))

        except Exception as e:
            # Planning is advisory - don't fail the translation if planning fails
            # Just log the error and continue
            import sys
            print(f"   ⚠️ Planning analysis failed (non-critical): {e}", file=sys.stderr, flush=True)

    def _extract_and_lock_terms(self, key_terms: list[dict]) -> None:
        """
        Extract terms from planning analysis and add to both GroundingBank and TranslationMemory.

        Args:
            key_terms: List of key term dictionaries from planning analysis.
        """
        for term_info in key_terms:
            term = term_info.get("term", "").strip()
            suggested = term_info.get("suggested_translation", "").strip()

            if term and suggested:
                if not hasattr(self.project, 'grounding') or not self.project.grounding:
                    from aat.storage.models import GroundingBank
                    self.project.grounding = GroundingBank()

                self.project.grounding.termbank.add_term(
                    source_term=term,
                    target_term=suggested,
                    examples=[term_info.get("context", "")],
                    confidence=0.8,
                )

                normalized = term.lower().strip()
                self.translation_memory.lock_term(normalized, suggested)

    def _draft_translate(self, segment: TranslationSegment, segment_index: int = 0, total_segments: int = 0) -> None:
        """
        Generate draft translation using LLM.

        Args:
            segment: TranslationSegment to translate.
            segment_index: Index of current segment for progress tracking.
            total_segments: Total number of segments for progress tracking.
        """
        import time
        import sys

        try:
            # Progress indicator
            progress_str = f"[{segment_index}/{total_segments}]" if total_segments > 0 else ""
            source_preview = segment.segment.source_text[:60].replace('\n', ' ') if segment.segment.source_text else ""
            print(f"📝 Translating {progress_str} {source_preview}...", file=sys.stderr, flush=True)
            start_time = time.time()

            # Extract planning analysis if available
            planning_analysis = None
            if segment.segment.metadata and "planning_analysis" in segment.segment.metadata:
                planning_analysis = segment.segment.metadata["planning_analysis"]

            # Build termbank dict from locked TM entries
            locked_terms = self.translation_memory.get_locked_terms()
            termbank_dict = None
            if locked_terms:
                termbank_dict = {e.source_phrase: e.target_phrase for e in locked_terms}

            # Build prompt with planning analysis and locked terms
            messages = DraftTranslationPrompt.build(
                source_text=segment.segment.source_text,
                context_before=segment.segment.context_before,
                context_after=segment.segment.context_after,
                termbank=termbank_dict,
                planning_analysis=planning_analysis,
            )

            # Get schema
            schema = DraftTranslationPrompt.get_response_schema()

            # Call LLM
            response = self.llm_client.chat(
                messages=messages,
                json_schema=schema,
                temperature=0.3,
            )

            elapsed = time.time() - start_time
            print(f"   ✓ Done in {elapsed:.1f}s", file=sys.stderr, flush=True)

            # Parse response
            content = response.get("content", {})
            if isinstance(content, dict):
                segment.translation = content.get("translation", "")
                uncertainties_data = content.get("uncertainties", [])

                # Parse uncertainties
                for unc_data in uncertainties_data:
                    segment.uncertainties.append(
                        UncertaintyItem(
                            type=unc_data.get("type", ""),
                            span=unc_data.get("span", ""),
                            question=unc_data.get("question", ""),
                            options=unc_data.get("options", []),
                        )
                    )

                # Parse notes
                notes_data = content.get("notes") or []
                segment.translation_notes.extend(notes_data)
            else:
                segment.translation = str(content)

        except LLMError as e:
            raise PipelineError(f"Failed to draft translate: {e}")
        except (json.JSONDecodeError, KeyError) as e:
            raise PipelineError(f"Failed to parse LLM response: {e}")

    def _deterministic_validate(self, segment: TranslationSegment) -> None:
        """
        Run deterministic validators on translation.

        Args:
            segment: TranslationSegment with translation.
        """
        if not segment.translation:
            return

        # Run all validators
        segment.validator_results = self.validators(
            segment.segment.source_text,
            segment.translation,
        )

    def _llm_critic_review(self, segment: TranslationSegment) -> None:
        """
        Run LLM critic review of translation.

        Args:
            segment: TranslationSegment with translation.
        """
        if not segment.translation:
            return

        try:
            # Build prompt
            messages = CriticReviewPrompt.build(
                source_text=segment.segment.source_text,
                translation=segment.translation,
            )

            # Get schema
            schema = CriticReviewPrompt.get_response_schema()

            # Call LLM
            response = self.llm_client.chat(
                messages=messages,
                json_schema=schema,
                temperature=0.2,
            )

            # Parse response
            content = response.get("content", {})
            if isinstance(content, dict):
                issues = content.get("issues", [])
                segment.critic_issues = issues
        except LLMError as e:
            raise PipelineError(f"Failed to run critic review: {e}")

    def _run_quality_heuristics(self, segment: TranslationSegment) -> None:
        """Run advisory quality heuristics on the translation.

        Results are stored in segment metadata but do not block the pipeline.
        """
        results = run_quality_heuristics(segment.translation)
        if not segment.segment.metadata:
            segment.segment.metadata = {}
        segment.segment.metadata["quality_heuristics"] = [
            {
                "name": r.name,
                "passed": r.passed,
                "score": r.score,
                "issues": [{"detail": i.detail, "span": i.span} for i in r.issues],
            }
            for r in results
        ]

    def _uncertainty_detect(self, segment: TranslationSegment) -> None:
        """
        Detect uncertainties requiring user attention.

        Args:
            segment: TranslationSegment to process.
        """
        # Check for LLM-reported uncertainties (already present from draft/review)
        if self._has_uncertainties(segment):
            return

        # Check for validator flags
        if self._has_validator_flags(segment):
            for result in segment.validator_results:
                if result.is_flag():
                    for issue in result.issues:
                        segment.uncertainties.append(
                            UncertaintyItem(
                                type="VALIDATOR_FLAG",
                                span=segment.segment.source_text,
                                question=f"Validator flag: {issue.code}",
                                options=[],
                            )
                        )

        # Run deterministic UncertaintyDetector on source text
        detector = UncertaintyDetector(min_confidence=self.config.uncertainty_min_confidence)
        detections = detector.detect_all(segment.segment.source_text)

        for category, items in detections.items():
            for item in items:
                segment.uncertainties.append(
                    UncertaintyItem(
                        type=item.get("type", category.upper()),
                        span=item.get("span", ""),
                        question=item.get("question", ""),
                        options=[],
                    )
                )

    def _revise(self, segment: TranslationSegment) -> None:
        """
        Revise translation based on critic issues and uncertainties via LLM.

        Args:
            segment: TranslationSegment to revise.
        """
        if not segment.translation:
            segment.uncertainties.clear()
            return

        try:
            locked_terms = self.translation_memory.get_locked_terms()
            termbank_dict = None
            if locked_terms:
                termbank_dict = {e.source_phrase: e.target_phrase for e in locked_terms}

            messages = RevisionPrompt.build(
                source_text=segment.segment.source_text,
                current_translation=segment.translation,
                critic_issues=segment.critic_issues,
                user_feedback=segment.user_comments,
                user_answers=(segment.segment.metadata or {}).get("uncertainty_answers", {}),
                termbank=termbank_dict,
            )

            schema = RevisionPrompt.get_response_schema()

            response = self.llm_client.chat(
                messages=messages,
                json_schema=schema,
                temperature=0.2,
            )

            content = response.get("content", {})
            if isinstance(content, dict):
                revised = content.get("translation", "")
                if revised:
                    segment.translation = revised

                # Parse notes from revision
                notes_data = content.get("notes") or []
                segment.translation_notes.extend(notes_data)

            segment.uncertainties.clear()

        except LLMError:
            segment.uncertainties.clear()

    def _should_block_on_validator_results(
        self, segment: TranslationSegment
    ) -> bool:
        """
        Check if pipeline should block on validator results.

        Args:
            segment: TranslationSegment with validator results.

        Returns:
            True if should block for user input.
        """
        if self.config.require_user_confirmation_on_fail:
            if has_any_failures(segment.validator_results):
                return True

        if self.config.require_user_confirmation_on_flag:
            if has_any_flags(segment.validator_results):
                return True

        return False

    def _has_uncertainties(self, segment: TranslationSegment) -> bool:
        """
        Check if segment has any uncertainties.

        Args:
            segment: TranslationSegment to check.

        Returns:
            True if any uncertainties exist.
        """
        return len(segment.uncertainties) > 0

    def _has_validator_flags(self, segment: TranslationSegment) -> bool:
        """
        Check if segment has any validator flags.

        Args:
            segment: TranslationSegment to check.

        Returns:
            True if any validator flags exist.
        """
        for result in segment.validator_results:
            if result.is_flag():
                return True
        return False

    def _create_segments_from_document(self) -> None:
        """
        Create translation segments from document paragraphs.

        This uses the segmenter to split paragraphs into
        segments of 200-400 tokens.
        """
        from aat.translate.segmenter import segment_paragraphs

        # Collect all paragraphs from document
        all_paragraphs = []
        for section in self.project.document.sections:
            all_paragraphs.extend(section.paragraphs)

        # Segment paragraphs
        segments = segment_paragraphs(all_paragraphs)

        # Create TranslationSegment objects
        self.project.segments = [
            TranslationSegment(
                segment=seg,
                state=SegmentState.ASSEMBLE_CONTEXT,
            )
            for seg in segments
        ]

    def _save_checkpoint(self) -> None:
        """
        Save checkpoint.

        Args:
            None
        """
        if not self.checkpoint_manager:
            return

        try:
            checkpoint = Checkpoint.create(self.project)
            self.checkpoint_manager.save_checkpoint(checkpoint)

            # Cleanup old checkpoints
            self.checkpoint_manager.cleanup_old_checkpoints(keep_count=10)
        except Exception as e:
            raise PipelineError(f"Failed to save checkpoint: {e}")


def run_pipeline(
    document_path: str,
    target_lang: str = "zh",
    config: PipelineConfig | None = None,
) -> TranslationProject:
    """
    Convenience function to run translation pipeline.

    Args:
        document_path: Path to input document.
        target_lang: Target language (default: zh).
        config: Pipeline configuration.

    Returns:
        TranslationProject with completed translation.

    Raises:
        PipelineError: If pipeline fails.
    """
    from aat.parsing.docx_parser import DocxParser

    # Parse document
    parser = DocxParser()
    document = parser.parse(document_path)

    # Create project
    project = TranslationProject.create(document)

    # Run pipeline
    pipeline = TranslationPipeline(project, config)
    return pipeline.run()
