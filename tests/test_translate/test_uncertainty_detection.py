"""Tests for uncertainty detection functionality."""

import pytest

from aat.translate.validators import UncertaintyDetector


class TestUncertaintyDetector:
    """Test suite for UncertaintyDetector."""

    def test_detect_ambiguous_pronouns(self):
        """Test detection of ambiguous pronouns."""
        detector = UncertaintyDetector()

        text = "This suggests it is important, but they didn't specify why."
        uncertainties = detector.detect_ambiguous_references(text)

        # Should detect "it" and "they" as potentially ambiguous
        assert len(uncertainties) >= 2
        spans = [u["span"] for u in uncertainties]
        assert "it" in spans
        assert "they" in spans

    def test_detect_unknown_terms(self):
        """Test detection of unknown/untranslated terms."""
        detector = UncertaintyDetector()

        text = "The concept of XYZ-123 remains unclear in the literature."
        uncertainties = detector.detect_unknown_terms(text)

        # Should detect XYZ-123 as potentially unknown
        assert len(uncertainties) >= 1
        assert any("XYZ-123" in u["span"] for u in uncertainties)

    def test_detect_figures_of_speech(self):
        """Test detection of idiomatic expressions."""
        detector = UncertaintyDetector()

        text = "The research paints a picture of the situation."
        uncertainties = detector.detect_figures_of_speech(text)

        # Should detect "paints a picture" as figurative language
        assert len(uncertainties) >= 1

    def test_detect_temporal_ambiguity(self):
        """Test detection of temporally ambiguous expressions."""
        detector = UncertaintyDetector()

        text = "The data shows this was significant at that time."
        uncertainties = detector.detect_temporal_ambiguity(text)

        # Should flag temporal references
        assert len(uncertainties) >= 1

    def test_run_all_detectors(self):
        """Test running all uncertainty detectors."""
        detector = UncertaintyDetector()

        text = "This suggests it is important, but they didn't specify the XYZ concept at that time."
        results = detector.detect_all(text)

        # Should return results from multiple detectors
        assert "ambiguous_references" in results
        assert "unknown_terms" in results
        assert "temporal_ambiguity" in results

    def test_empty_text(self):
        """Test handling of empty text."""
        detector = UncertaintyDetector()

        results = detector.detect_all("")

        # Should return empty results for all detectors
        for uncertainties in results.values():
            assert len(uncertainties) == 0

    def test_confidence_thresholds(self):
        """Test that confidence thresholds filter low-confidence detections."""
        detector = UncertaintyDetector(min_confidence=0.7)

        # Text with clear ambiguity
        text = "It is unclear who they were referring to."
        results = detector.detect_ambiguous_references(text)

        # All detected uncertainties should meet confidence threshold
        for uncertainty in results:
            assert uncertainty.get("confidence", 0) >= 0.7


class TestUncertaintyIntegration:
    """Integration tests for uncertainty detection."""

    def test_uncertainty_in_translation_segment(self):
        """Test that uncertainties can be stored in translation segments."""
        from aat.storage.models import Segment, TranslationSegment, SegmentState

        # Create a segment with uncertainty
        segment = TranslationSegment(
            segment=Segment(
                sid="test-1",
                pid_list=["p1"],
                source_text="This is ambiguous.",
            ),
            state=SegmentState.DRAFT_TRANSLATE,
        )

        # Add uncertainty item
        from aat.storage.models import UncertaintyItem
        segment.uncertainties.append(UncertaintyItem(
            type="MEANING",
            span="This",
            question="What does 'This' refer to?",
            options=["Option A", "Option B"],
        ))

        assert len(segment.uncertainties) == 1
        assert segment.uncertainties[0].type == "MEANING"

    def test_uncertainty_from_llm_response(self):
        """Test parsing uncertainties from LLM response."""
        from aat.storage.models import UncertaintyItem

        # Simulate LLM response data
        uncertainties_data = [
            {
                "type": "TERM",
                "span": "XYZ",
                "question": "What is the correct translation of XYZ?",
                "options": ["选项A", "选项B"],
            },
            {
                "type": "MEANING",
                "span": "it",
                "question": "What does 'it' refer to?",
                "options": [],
            },
        ]

        # Parse into UncertaintyItems
        uncertainties = []
        for data in uncertainties_data:
            uncertainties.append(UncertaintyItem(
                type=data.get("type", ""),
                span=data.get("span", ""),
                question=data.get("question", ""),
                options=data.get("options", []),
            ))

        assert len(uncertainties) == 2
        assert uncertainties[0].type == "TERM"
        assert uncertainties[1].type == "MEANING"