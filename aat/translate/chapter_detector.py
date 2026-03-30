"""Chapter detection for academic documents."""

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from aat.storage.models import Paragraph, Section


@dataclass
class ChapterInfo:
    """Information about a detected chapter."""

    chapter_id: str
    title: str | None
    start_idx: int  # Index of first paragraph in chapter
    end_idx: int | None = None  # Index of last paragraph (None if open)
    level: int = 1  # Heading level (1 = top level)


class ChapterDetector:
    """Detect chapters in academic documents."""

    # Patterns for chapter detection
    CHAPTER_PATTERNS = [
        # "Chapter X" or "CHAPTER X"
        r"^(?:Chapter|CHAPTER)\s+(\d+|I+|A-Z)",
        # "X. Title" or "X Title" (number followed by space/title)
        r"^(\d+)\.?\s+([A-Z][^a-z]*|[A-Z][a-z]+)",
        # "1 Introduction" style (common in dissertations)
        r"^(\d+)\s+([A-Z][a-zA-Z\s]+)$",
    ]

    # Section headings that indicate new chapters/major sections
    MAJOR_SECTION_KEYWORDS = [
        "introduction",
        "background",
        "literature review",
        "methodology",
        "methods",
        "results",
        "discussion",
        "conclusion",
        "references",
        "appendix",
        "acknowledgments",
    ]

    def __init__(self) -> None:
        """Initialize the chapter detector."""
        self._compiled_patterns = [re.compile(p, re.IGNORECASE) for p in self.CHAPTER_PATTERNS]

    def detect_chapters_from_paragraphs(
        self,
        paragraphs: list["Paragraph"],
        heading_style_map: dict[str, int] | None = None,
    ) -> list[ChapterInfo]:
        """
        Detect chapters from a list of paragraphs.

        Args:
            paragraphs: List of paragraphs to analyze.
            heading_style_map: Optional mapping of paragraph IDs to heading levels.
                               (e.g., {"para_1": 1} means paragraph 1 is Heading 1)

        Returns:
            List of detected chapters.
        """
        chapters: list[ChapterInfo] = []
        current_chapter: ChapterInfo | None = None

        for idx, para in enumerate(paragraphs):
            text = para.text.strip()
            if not text:
                continue

            # Check if this paragraph is a chapter heading
            heading_level = self._get_heading_level(para, heading_style_map)
            is_chapter_start = self._is_chapter_heading(text, heading_level)

            if is_chapter_start:
                # Close previous chapter
                if current_chapter:
                    current_chapter.end_idx = idx - 1
                    chapters.append(current_chapter)

                # Start new chapter
                chapter_title = self._extract_chapter_title(text)
                current_chapter = ChapterInfo(
                    chapter_id=f"chapter_{len(chapters) + 1:03d}",
                    title=chapter_title,
                    start_idx=idx,
                    level=heading_level or 1,
                )

        # Close final chapter
        if current_chapter:
            current_chapter.end_idx = len(paragraphs) - 1
            chapters.append(current_chapter)

        # If no chapters detected, treat entire document as one chapter
        if not chapters and paragraphs:
            chapters.append(
                ChapterInfo(
                    chapter_id="chapter_001",
                    title=None,
                    start_idx=0,
                    end_idx=len(paragraphs) - 1,
                )
            )

        return chapters

    def assign_chapters_to_segments(
        self,
        chapters: list[ChapterInfo],
        paragraph_ids: list[str],
    ) -> dict[str, str]:
        """
        Create a mapping from paragraph IDs to chapter IDs.

        Args:
            chapters: List of detected chapters.
            paragraph_ids: List of paragraph IDs in order.

        Returns:
            Dictionary mapping paragraph ID to chapter ID.
        """
        mapping: dict[str, str] = {}

        for chapter in chapters:
            start_idx = chapter.start_idx
            end_idx = chapter.end_idx or len(paragraph_ids) - 1

            for idx in range(start_idx, min(end_idx + 1, len(paragraph_ids))):
                mapping[paragraph_ids[idx]] = chapter.chapter_id

        return mapping

    def _get_heading_level(
        self,
        paragraph: "Paragraph",
        heading_style_map: dict[str, int] | None,
    ) -> int | None:
        """Get heading level for a paragraph if it's a heading."""
        if heading_style_map and paragraph.pid in heading_style_map:
            return heading_style_map[paragraph.pid]

        # Check text patterns that indicate headings
        text = paragraph.text.strip()
        if text.startswith("#"):
            # Markdown-style heading
            return len(text) - len(text.lstrip("#"))

        return None

    def _is_chapter_heading(self, text: str, heading_level: int | None) -> bool:
        """Check if text is a chapter heading."""
        text = text.strip()
        lower = text.lower()

        # Check explicit "Chapter X" pattern
        if re.match(r"^(Chapter|CHAPTER)\s+\d+", text, re.IGNORECASE):
            return True

        # Check if it's a top-level heading (level 1)
        if heading_level == 1:
            return True

        # Check for numbered sections that look like chapters
        # Pattern: "1 Introduction" or "1. Introduction"
        if re.match(r"^\d+\.?\s+[A-Z]", text):
            # Check if this looks like a major section
            first_word = text.split()[1] if len(text.split()) > 1 else ""
            if first_word.lower() in self.MAJOR_SECTION_KEYWORDS:
                return True
            # Long title suggests major section
            if len(text) > 20:
                return True

        # Check for major section keywords without numbers
        for keyword in self.MAJOR_SECTION_KEYWORDS:
            if lower.startswith(keyword) and len(text) < 50:
                return True

        return False

    def _extract_chapter_title(self, text: str) -> str | None:
        """Extract clean chapter title from heading text."""
        text = text.strip()

        # Remove "Chapter X" prefix
        text = re.sub(r"^(Chapter|CHAPTER)\s+\d+[:.]?\s*", "", text, flags=re.IGNORECASE)

        # Remove leading number
        text = re.sub(r"^\d+\.?\s*", "", text)

        return text if text else None
