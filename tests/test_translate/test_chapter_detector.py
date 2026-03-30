"""Tests for chapter detection functionality."""

import pytest

from aat.storage.models import Paragraph
from aat.translate.chapter_detector import ChapterDetector, ChapterInfo


class TestChapterDetector:
    """Test suite for ChapterDetector."""

    def test_detect_chapters_chapter_pattern(self):
        """Test detecting 'Chapter X' pattern."""
        detector = ChapterDetector()

        paragraphs = [
            Paragraph(pid="p1", text="Chapter 1 Introduction"),
            Paragraph(pid="p2", text="This is the introduction content."),
            Paragraph(pid="p3", text="Chapter 2 Literature Review"),
            Paragraph(pid="p4", text="This is the literature review."),
        ]

        chapters = detector.detect_chapters_from_paragraphs(paragraphs)

        assert len(chapters) == 2
        assert chapters[0].chapter_id == "chapter_001"
        assert chapters[0].title == "Introduction"
        assert chapters[1].chapter_id == "chapter_002"
        assert chapters[1].title == "Literature Review"

    def test_detect_chapters_numbered_sections(self):
        """Test detecting numbered section headings."""
        detector = ChapterDetector()

        paragraphs = [
            Paragraph(pid="p1", text="1 Introduction"),
            Paragraph(pid="p2", text="Some intro text here that is long enough to be considered content." * 5),
            # Need title > 20 chars to be detected as chapter
            Paragraph(pid="p3", text="2 Literature Review Section"),
            Paragraph(pid="p4", text="Some literature text here that is also long enough for content." * 5),
        ]

        chapters = detector.detect_chapters_from_paragraphs(paragraphs)

        # Both numbered sections should be detected as chapters
        assert len(chapters) == 2
        assert chapters[0].title == "Introduction"
        assert chapters[1].title == "Literature Review Section"

    def test_detect_chapters_major_section_keywords(self):
        """Test detecting major section keywords."""
        detector = ChapterDetector()

        paragraphs = [
            Paragraph(pid="p1", text="Introduction"),
            Paragraph(pid="p2", text="Intro content."),
            Paragraph(pid="p3", text="Methodology"),
            Paragraph(pid="p4", text="Methods content."),
            Paragraph(pid="p5", text="Results"),
            Paragraph(pid="p6", text="Results content."),
        ]

        chapters = detector.detect_chapters_from_paragraphs(paragraphs)

        assert len(chapters) >= 2  # Should detect at least some sections
        # Check that major sections are detected
        titles = [c.title for c in chapters if c.title]
        assert any("Intro" in t or "Methodology" in t or "Results" in t for t in titles)

    def test_detect_chapters_no_chapters(self):
        """Test handling document with no clear chapters."""
        detector = ChapterDetector()

        paragraphs = [
            Paragraph(pid="p1", text="This is just some content."),
            Paragraph(pid="p2", text="More content here."),
            Paragraph(pid="p3", text="Even more content."),
        ]

        chapters = detector.detect_chapters_from_paragraphs(paragraphs)

        # Should create one chapter for entire document
        assert len(chapters) == 1
        assert chapters[0].chapter_id == "chapter_001"
        assert chapters[0].start_idx == 0
        assert chapters[0].end_idx == 2

    def test_assign_chapters_to_segments(self):
        """Test assigning chapters to segment paragraphs."""
        detector = ChapterDetector()

        chapters = [
            ChapterInfo(chapter_id="ch1", title="Intro", start_idx=0, end_idx=1),
            ChapterInfo(chapter_id="ch2", title="Body", start_idx=2, end_idx=3),
        ]

        paragraph_ids = ["p1", "p2", "p3", "p4"]

        mapping = detector.assign_chapters_to_segments(chapters, paragraph_ids)

        assert mapping["p1"] == "ch1"
        assert mapping["p2"] == "ch1"
        assert mapping["p3"] == "ch2"
        assert mapping["p4"] == "ch2"


class TestChapterDetectionIntegration:
    """Integration tests for chapter detection with segmenter."""

    def test_segmenter_preserves_chapter_info(self):
        """Test that segmenter correctly assigns chapter IDs to segments."""
        from aat.translate.segmenter import Segmenter

        paragraphs = [
            Paragraph(pid="p1", text="Chapter 1 Introduction"),
            Paragraph(pid="p2", text="This is the introduction content with some text." * 10),
            Paragraph(pid="p3", text="More intro content here." * 10),
            Paragraph(pid="p4", text="Chapter 2 Literature Review"),
            Paragraph(pid="p5", text="This is the literature review content." * 10),
        ]

        segmenter = Segmenter()
        segments = segmenter.segment_paragraphs(paragraphs)

        # Should have segments with chapter IDs
        assert len(segments) > 0

        # Check that segments have chapter_id attribute
        for seg in segments:
            assert hasattr(seg, "chapter_id")

        # Some segments should have chapter IDs
        segments_with_chapters = [s for s in segments if s.chapter_id]
        assert len(segments_with_chapters) > 0

    def test_chapter_boundary_respected(self):
        """Test that chapter boundaries are respected during segmentation."""
        from aat.translate.segmenter import Segmenter

        paragraphs = [
            Paragraph(pid="p1", text="1 Introduction"),
            Paragraph(pid="p2", text="This is content for chapter 1 that is long enough to create a substantial segment for testing chapter boundary detection. " * 10),
            Paragraph(pid="p3", text="2 Methods"),
            Paragraph(pid="p4", text="This is content for chapter 2 that is also long enough to create a substantial segment for testing chapter boundary detection. " * 10),
        ]

        segmenter = Segmenter()
        segments = segmenter.segment_paragraphs(paragraphs)

        # Find segments for each chapter
        ch1_segments = [s for s in segments if s.chapter_id and "001" in s.chapter_id]
        ch2_segments = [s for s in segments if s.chapter_id and "002" in s.chapter_id]

        # Both chapters should have segments
        assert len(ch1_segments) > 0, "Chapter 1 should have segments"
        assert len(ch2_segments) > 0, "Chapter 2 should have segments"
