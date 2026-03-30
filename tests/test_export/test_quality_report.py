"""Tests for quality report generation."""

import pytest

from aat.storage.models import (
    DocumentModel,
    Segment,
    SegmentState,
    TranslationProject,
    TranslationSegment,
    UncertaintyItem,
    ValidationResult,
    ValidatorIssue,
    ValidatorStatus,
)
from aat.export.quality_report import QualityReport, generate_quality_report


class TestQualityReport:
    """Test QualityReport dataclass."""

    def test_to_text_renders_correctly(self):
        report = QualityReport(
            source_document="test.pdf",
            total_segments=10,
            chapters_detected=3,
            planning_analyses=10,
            total_revision_rounds=5,
            avg_revision_rounds=0.5,
            uncertainties_flagged=2,
            citation_accuracy=100.0,
            numeric_accuracy=100.0,
            total_notes=15,
            avg_notes_per_segment=1.5,
        )
        text = report.to_text()
        assert "Translation Quality Report" in text
        assert "test.pdf" in text
        assert "10" in text
        assert "3" in text
        assert "100.0%" in text

    def test_to_dict_returns_dict(self):
        report = QualityReport(source_document="test.pdf", total_segments=5)
        d = report.to_dict()
        assert isinstance(d, dict)
        assert d["source_document"] == "test.pdf"
        assert d["total_segments"] == 5

    def test_default_values(self):
        report = QualityReport()
        assert report.total_segments == 0
        assert report.citation_accuracy == 100.0
        assert report.total_notes == 0


class TestGenerateQualityReport:
    """Test generate_quality_report function."""

    def _make_project(self, segments: list[TranslationSegment] | None = None) -> TranslationProject:
        doc = DocumentModel.create()
        doc.title = "Test Document"
        project = TranslationProject.create(doc)
        if segments:
            project.segments = segments
        return project

    def _make_segment(
        self,
        sid: str = "s1",
        translation: str = "翻译。",
        locked: bool = True,
        metadata: dict | None = None,
        notes: list[str] | None = None,
        validator_results: list | None = None,
        uncertainties: list | None = None,
    ) -> TranslationSegment:
        seg = Segment(sid=sid, pid_list=["p1"], source_text="Test.", metadata=metadata or {})
        ts = TranslationSegment(
            segment=seg,
            state=SegmentState.LOCK_SEGMENT,
            translation=translation,
            locked=locked,
            translation_notes=notes or [],
            validator_results=validator_results or [],
            uncertainties=uncertainties or [],
        )
        return ts

    def test_empty_project_no_crash(self):
        project = self._make_project()
        report = generate_quality_report(project)
        assert report.total_segments == 0
        assert report.citation_accuracy == 100.0
        assert report.total_notes == 0
        text = report.to_text()
        assert "Translation Quality Report" in text

    def test_counts_segments(self):
        segs = [self._make_segment(sid=f"s{i}") for i in range(5)]
        project = self._make_project(segs)
        report = generate_quality_report(project)
        assert report.total_segments == 5

    def test_counts_planning_analyses(self):
        seg = self._make_segment(
            metadata={"planning_analysis": {"segment_type": "其他"}}
        )
        project = self._make_project([seg])
        report = generate_quality_report(project)
        assert report.planning_analyses == 1

    def test_counts_revisions(self):
        seg = self._make_segment(metadata={"revision_count": 3})
        project = self._make_project([seg])
        report = generate_quality_report(project)
        assert report.total_revision_rounds == 3
        assert report.avg_revision_rounds == 3.0

    def test_counts_force_locked(self):
        seg = self._make_segment(metadata={"force_locked": True, "force_lock_reason": "max_revision_rounds_exceeded"})
        project = self._make_project([seg])
        report = generate_quality_report(project)
        assert report.force_locked_segments == 1

    def test_counts_notes(self):
        seg = self._make_segment(notes=["Note 1", "Note 2", "Note 3"])
        project = self._make_project([seg])
        report = generate_quality_report(project)
        assert report.total_notes == 3
        assert report.avg_notes_per_segment == 3.0

    def test_counts_quality_heuristics(self):
        seg = self._make_segment(metadata={
            "quality_heuristics": [
                {"name": "calque_detector", "passed": False, "issues": [{"detail": "calque"}]},
                {"name": "readability_scorer", "passed": True, "score": 75.0, "issues": []},
                {"name": "repetition_detector", "passed": True, "issues": []},
                {"name": "academic_tone_checker", "passed": False, "issues": [{"detail": "informal"}]},
            ]
        })
        project = self._make_project([seg])
        report = generate_quality_report(project)
        assert report.calque_suspects == 1
        assert report.readability_avg == 75.0
        assert report.informal_markers == 1

    def test_citation_failure_lowers_accuracy(self):
        seg = self._make_segment(
            validator_results=[
                ValidationResult(
                    status=ValidatorStatus.FAIL,
                    issues=[ValidatorIssue(code="CITATION_MISMATCH", detail="Missing citation")]
                ),
            ]
        )
        project = self._make_project([seg])
        report = generate_quality_report(project)
        assert report.citation_accuracy == 0.0

    def test_length_flags_counted_from_flag_status(self):
        seg = self._make_segment(
            validator_results=[
                ValidationResult(
                    status=ValidatorStatus.FLAG,
                    issues=[ValidatorIssue(code="LENGTH_EXCESSIVE", detail="Ratio 1.8")]
                ),
            ]
        )
        project = self._make_project([seg])
        report = generate_quality_report(project)
        assert report.length_flags == 1

    def test_to_text_includes_terminology_section(self):
        report = QualityReport(locked_terms=10, tm_entries_total=50)
        text = report.to_text()
        assert "Terminology" in text
        assert "Locked terms" in text

    def test_to_text_and_to_dict_consistency(self):
        seg = self._make_segment(notes=["A note"])
        project = self._make_project([seg])
        report = generate_quality_report(project)
        text = report.to_text()
        d = report.to_dict()
        assert "Translation Quality Report" in text
        assert d["total_notes"] == 1
