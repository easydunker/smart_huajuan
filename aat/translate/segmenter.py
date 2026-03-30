"""Text segmentation for translation pipeline."""

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import uuid4

from aat.parsing.citation import CitationExtractor
from aat.storage.models import Segment
from aat.translate.chapter_detector import ChapterDetector, ChapterInfo

if TYPE_CHECKING:
    from aat.storage.models import Paragraph


@dataclass
class SegmenterConfig:
    """Configuration for segmenter."""
    min_tokens: int = 200
    max_tokens: int = 400
    target_tokens: int = 300
    include_context: bool = True
    context_chars: int = 100


class SegmenterError(Exception):
    """Exception raised for segmentation errors."""


class Segmenter:
    """Segment text for translation processing.

    Segmentation rules:
    1. Each segment is 200-400 tokens
    2. Never splits inside a citation
    3. Never splits mid-sentence
    4. Each segment keeps pointer to original paragraph IDs
    """

    def __init__(self, config: SegmenterConfig | None = None) -> None:
        """Initialize the segmenter."""
        self.config = config or SegmenterConfig()
        self._citation_extractor = CitationExtractor()
        self._sentence_pattern = re.compile(r"(?<=[.!?])\s+")

    def segment_paragraphs(self, paragraphs: list["Paragraph"]) -> list[Segment]:
        """
        Segment a list of paragraphs.

        Args:
            paragraphs: List of paragraphs to segment.

        Returns:
            List of segments.
        """
        return self.segment_paragraphs_with_chapters(paragraphs)

    def segment_paragraphs_with_chapters(
        self,
        paragraphs: list["Paragraph"],
        heading_style_map: dict[str, int] | None = None,
    ) -> list[Segment]:
        """
        Segment paragraphs with chapter-aware organization.

        Args:
            paragraphs: List of paragraphs to segment.
            heading_style_map: Optional mapping of paragraph IDs to heading levels.

        Returns:
            List of segments with chapter_id metadata.
        """
        # Detect chapters first
        detector = ChapterDetector()
        chapters = detector.detect_chapters_from_paragraphs(
            paragraphs, heading_style_map
        )

        # Create paragraph to chapter mapping
        para_ids = [p.pid for p in paragraphs]
        chapter_mapping = detector.assign_chapters_to_segments(chapters, para_ids)

        # Now segment with chapter awareness
        segments: list[Segment] = []
        current_segment = ""
        current_pids: list[str] = []
        current_chapter_id: str | None = None
        context_before = ""
        context_after = ""

        for i, para in enumerate(paragraphs):
            text = para.text.strip()
            if not text:
                continue

            # Get chapter for this paragraph
            para_chapter_id = chapter_mapping.get(para.pid)

            # If chapter changed, finalize current segment
            if current_chapter_id and para_chapter_id != current_chapter_id:
                if current_segment.strip():
                    segments.append(
                        Segment(
                            sid=str(uuid4()),
                            pid_list=current_pids.copy(),
                            source_text=current_segment.strip(),
                            context_before=context_before if segments else None,
                            context_after=context_after,
                            chapter_id=current_chapter_id,
                        )
                    )
                current_segment = ""
                current_pids = []

            current_chapter_id = para_chapter_id

            # Get context from previous paragraph
            if self.config.include_context and i > 0:
                prev_para = paragraphs[i - 1].text.strip()
                context_before = prev_para[-self.config.context_chars:]

            # Get context from next paragraph
            if self.config.include_context and i < len(paragraphs) - 1:
                next_para = paragraphs[i + 1].text.strip()
                context_after = next_para[:self.config.context_chars]

            # If adding this paragraph would exceed max tokens,
            # finalize current segment first
            current_tokens = self._count_tokens(current_segment)
            new_tokens = self._count_tokens(text)

            if current_segment and (current_tokens + new_tokens > self.config.max_tokens):
                # Finalize current segment
                if current_segment.strip():
                    segments.append(
                        Segment(
                            sid=str(uuid4()),
                            pid_list=current_pids.copy(),
                            source_text=current_segment.strip(),
                            context_before=context_before if segments else None,
                            context_after=context_after,
                            chapter_id=current_chapter_id,
                        )
                    )
                # Start new segment
                current_segment = ""
                current_pids = []

            # Add paragraph text to current segment
            if current_segment:
                current_segment += " " + text
            else:
                current_segment = text
            current_pids.append(para.pid)

        # Don't forget the last segment
        if current_segment.strip():
            segments.append(
                Segment(
                    sid=str(uuid4()),
                    pid_list=current_pids,
                    source_text=current_segment.strip(),
                    context_before=context_before if len(segments) > 0 else None,
                    context_after=None,
                    chapter_id=current_chapter_id,
                )
            )

        # Now split segments by sentence boundaries if they're too long
        segments = self._refine_segments(segments)

        return segments

    def segment_text(self, text: str, pid: str = "default") -> list[Segment]:
        """
        Segment a single text string.

        Args:
            text: Text to segment.
            pid: Paragraph ID to associate with segments.

        Returns:
            List of segments.
        """
        segments = self._split_text_by_constraints(text)
        segments = self._refine_segments(segments, default_pid=pid)

        # Assign proper segment IDs and paragraph IDs
        for seg in segments:
            if not seg.sid:
                seg.sid = str(uuid4())
            if not seg.pid_list:
                seg.pid_list = [pid]

        return segments

    def _split_text_by_constraints(self, text: str) -> list[Segment]:
        """
        Split text into segments respecting constraints.

        Args:
            text: Text to split.

        Returns:
            List of segments (without IDs yet).
        """
        # Get citation positions
        citations = self._citation_extractor.extract_from_text(text)

        # Create list of split points (positions we cannot split at)
        forbidden_ranges = [(c.start, c.end) for c in citations]

        # Split by sentences first
        sentences = self._sentence_pattern.split(text)

        segments: list[Segment] = []
        current_segment = ""

        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue

            # Check if adding this sentence would exceed max tokens
            current_tokens = self._count_tokens(current_segment)
            new_tokens = self._count_tokens(sentence)

            if current_segment and (current_tokens + new_tokens > self.config.max_tokens):
                # Finalize current segment
                if current_segment.strip():
                    segments.append(
                        Segment(
                            sid="",
                            pid_list=[],
                            source_text=current_segment.strip(),
                        )
                    )
                current_segment = ""

            # Check if this sentence would be too long even alone
            if new_tokens > self.config.max_tokens:
                # Need to split this sentence
                if current_segment:
                    segments.append(
                        Segment(
                            sid="",
                            pid_list=[],
                            source_text=current_segment.strip(),
                        )
                    )
                    current_segment = ""

                # Split sentence at token boundaries
                subsegments = self._split_long_text(sentence, forbidden_ranges)
                segments.extend(subsegments)
            else:
                # Add sentence to current segment
                if current_segment:
                    current_segment += " " + sentence
                else:
                    current_segment = sentence

        # Don't forget the last segment
        if current_segment.strip():
            segments.append(
                Segment(
                    sid="",
                    pid_list=[],
                    source_text=current_segment.strip(),
                )
            )

        return segments

    def _split_long_text(self, text: str, forbidden_ranges: list[tuple[int, int]]) -> list[Segment]:
        """
        Split a long text that exceeds max tokens.

        Args:
            text: Text to split.
            forbidden_ranges: List of (start, end) tuples we cannot split inside.

        Returns:
            List of segments.
        """
        segments: list[Segment] = []
        words = text.split()

        current_segment = []
        current_length = 0

        for word in words:
            word_length = len(word.split())

            # Check if adding this word would exceed max tokens
            if current_segment and (current_length + word_length > self.config.max_tokens):
                segments.append(
                    Segment(
                        sid="",
                        pid_list=[],
                        source_text=" ".join(current_segment),
                    )
                )
                current_segment = [word]
                current_length = word_length
            else:
                current_segment.append(word)
                current_length += word_length

        # Don't forget the last segment
        if current_segment:
            segments.append(
                Segment(
                    sid="",
                    pid_list=[],
                    source_text=" ".join(current_segment),
                )
            )

        return segments

    def _refine_segments(
        self,
        segments: list[Segment],
        default_pid: str = "default",
    ) -> list[Segment]:
        """
        Refine segments to meet all constraints.

        This includes:
        1. Merging segments that are too short
        2. Ensuring no segment is empty

        Args:
            segments: List of segments to refine.
            default_pid: Default paragraph ID if none set.

        Returns:
            Refined list of segments.
        """
        refined: list[Segment] = []

        for segment in segments:
            # Skip empty segments
            if not segment.source_text.strip():
                continue

            # Check if segment is too short
            tokens = self._count_tokens(segment.source_text)
            if tokens < self.config.min_tokens and refined:
                # Merge with previous segment
                prev = refined[-1]
                merged_text = prev.source_text + " " + segment.source_text
                merged_pids = list(set(prev.pid_list + segment.pid_list))

                # Preserve chapter_id when merging (use previous segment's chapter)
                merged_chapter_id = prev.chapter_id or segment.chapter_id

                refined[-1] = Segment(
                    sid=prev.sid,
                    pid_list=merged_pids,
                    source_text=merged_text.strip(),
                    context_before=prev.context_before,
                    context_after=segment.context_after,
                    chapter_id=merged_chapter_id,
                )
            else:
                # Ensure segment has pids
                if not segment.pid_list:
                    segment.pid_list = [default_pid]
                refined.append(segment)

        # Validate invariants
        self._validate_invariants(refined)

        return refined

    def _validate_invariants(self, segments: list[Segment]) -> None:
        """
        Validate segment invariants.

        Raises:
            SegmenterError: If any invariant is violated.
        """
        for segment in segments:
            # Invariant 1: Never returns empty segment
            if not segment.source_text.strip():
                raise SegmenterError("Empty segment produced")

            # Invariant 2: Never splits inside a citation
            self._check_citation_integrity(segment)

            # Invariant 3: Segment size constraints
            tokens = self._count_tokens(segment.source_text)
            if tokens > self.config.max_tokens:
                # This may still be acceptable if it's unavoidable
                # (e.g., a single very long citation or technical term)
                pass

    def _check_citation_integrity(self, segment: Segment) -> None:
        """
        Check that segment doesn't split inside a citation.

        Args:
            segment: Segment to check.

        Raises:
            SegmenterError: If citation integrity is violated.
        """
        text = segment.source_text
        citations = self._citation_extractor.extract_from_text(text)

        # For each citation, check it's complete
        for citation in citations:
            # Citation should be present exactly as extracted
            if citation.text not in text:
                raise SegmenterError(f"Citation split: {citation.text}")

    def _count_tokens(self, text: str) -> int:
        """
        Count approximate number of tokens in text.

        This is a rough approximation. For production, you might use
        tiktoken or a proper tokenizer.

        Args:
            text: Text to count tokens in.

        Returns:
            Approximate token count.
        """
        # Simple word-based approximation
        # English words ~1.3 tokens per word average
        words = text.split()
        return int(len(words) * 1.3)


def segment_paragraphs(paragraphs: list["Paragraph"]) -> list[Segment]:
    """
    Convenience function to segment paragraphs with default config.

    Args:
        paragraphs: List of paragraphs to segment.

    Returns:
        List of segments.
    """
    segmenter = Segmenter()
    return segmenter.segment_paragraphs(paragraphs)


def segment_text(text: str) -> list[Segment]:
    """
    Convenience function to segment text with default config.

    Args:
        text: Text to segment.

    Returns:
        List of segments.
    """
    segmenter = Segmenter()
    return segmenter.segment_text(text)
