"""Quality report generation for translation projects."""

from dataclasses import dataclass, field
from typing import Any

from aat.storage.models import TranslationProject, TranslationSegment


@dataclass
class QualityReport:
    """Structured quality report for a translation run."""

    # Input
    source_document: str = ""
    total_segments: int = 0
    chapters_detected: int = 0

    # Process
    planning_analyses: int = 0
    total_revision_rounds: int = 0
    avg_revision_rounds: float = 0.0
    uncertainties_flagged: int = 0
    uncertainties_unresolved: int = 0

    # Validation
    citation_accuracy: float = 100.0
    numeric_accuracy: float = 100.0
    length_flags: int = 0

    # Quality heuristics
    calque_suspects: int = 0
    readability_avg: float = 100.0
    readability_below_60: int = 0
    repetition_flags: int = 0
    informal_markers: int = 0

    # Terminology
    locked_terms: int = 0
    tm_entries_total: int = 0

    # Output
    total_notes: int = 0
    avg_notes_per_segment: float = 0.0

    # Force-locked segments
    force_locked_segments: int = 0

    def to_text(self) -> str:
        """Render report as human-readable text."""
        lines = [
            "Translation Quality Report",
            "==========================",
            "",
            "Input",
            f"  Source document:    {self.source_document}",
            f"  Total segments:    {self.total_segments}",
            f"  Chapters detected: {self.chapters_detected}",
            "",
            "Process",
            f"  Planning analyses:  {self.planning_analyses} / {self.total_segments}",
            f"  Revision rounds:    {self.total_revision_rounds} (avg {self.avg_revision_rounds:.2f} per segment)",
            f"  Uncertainties:      {self.uncertainties_flagged} flagged, {self.uncertainties_unresolved} unresolved",
            f"  Force-locked:       {self.force_locked_segments} segments",
            "",
            "Validation",
            f"  Citation accuracy:  {self.citation_accuracy:.1f}%",
            f"  Numeric accuracy:   {self.numeric_accuracy:.1f}%",
            f"  Length flags:        {self.length_flags} segments",
            "",
            "Quality Heuristics",
            f"  Calque suspects:    {self.calque_suspects} segments",
            f"  Readability:        avg {self.readability_avg:.1f}/100 ({self.readability_below_60} segments below 60)",
            f"  Repetition flags:   {self.repetition_flags} segments",
            f"  Informal markers:   {self.informal_markers} segments",
            "",
            "Terminology",
            f"  Locked terms:       {self.locked_terms}",
            f"  TM entries total:   {self.tm_entries_total}",
            "",
            "Output",
            f"  Translation notes:  {self.total_notes} total",
            f"  Avg notes/segment:  {self.avg_notes_per_segment:.1f}",
        ]
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        """Render report as dictionary."""
        from dataclasses import asdict
        return asdict(self)


def generate_quality_report(project: TranslationProject) -> QualityReport:
    """Generate a quality report from a completed translation project.

    Args:
        project: The TranslationProject with completed segments.

    Returns:
        QualityReport with computed metrics.
    """
    report = QualityReport()

    report.source_document = project.document.title or "Unknown"
    report.total_segments = len(project.segments)

    chapter_ids = set()
    for seg in project.segments:
        cid = getattr(seg.segment, "chapter_id", None)
        if cid:
            chapter_ids.add(cid)
    report.chapters_detected = len(chapter_ids)

    if not project.segments:
        return report

    total_revisions = 0
    total_notes = 0
    planning_count = 0
    uncertainties_flagged = 0
    force_locked = 0

    citation_failures = 0
    numeric_failures = 0
    length_flags = 0

    calque_count = 0
    readability_scores: list[float] = []
    repetition_count = 0
    informal_count = 0

    for seg in project.segments:
        metadata = seg.segment.metadata or {}

        if "planning_analysis" in metadata:
            planning_count += 1

        revision_count = metadata.get("revision_count", 0)
        total_revisions += revision_count

        if metadata.get("force_locked"):
            force_locked += 1

        total_notes += len(seg.translation_notes)
        uncertainties_flagged += len(seg.uncertainties)

        has_citation_failure = False
        has_numeric_failure = False
        for result in seg.validator_results:
            if result.is_fail():
                for issue in result.issues:
                    if issue.code == "CITATION_MISMATCH":
                        has_citation_failure = True
                    elif issue.code == "NUMERIC_MISMATCH":
                        has_numeric_failure = True
            if result.is_flag() or result.is_fail():
                for issue in result.issues:
                    if issue.code == "LENGTH_EXCESSIVE":
                        length_flags += 1
        if has_citation_failure:
            citation_failures += 1
        if has_numeric_failure:
            numeric_failures += 1

        quality_data = metadata.get("quality_heuristics", [])
        for heuristic in quality_data:
            name = heuristic.get("name", "")
            if name == "calque_detector" and not heuristic.get("passed", True):
                calque_count += 1
            elif name == "readability_scorer":
                score = heuristic.get("score")
                if score is not None:
                    readability_scores.append(score)
            elif name == "repetition_detector" and not heuristic.get("passed", True):
                repetition_count += 1
            elif name == "academic_tone_checker" and not heuristic.get("passed", True):
                informal_count += 1

    report.planning_analyses = planning_count
    report.total_revision_rounds = total_revisions
    report.avg_revision_rounds = total_revisions / report.total_segments if report.total_segments else 0.0
    report.uncertainties_flagged = uncertainties_flagged
    report.force_locked_segments = force_locked
    report.total_notes = total_notes
    report.avg_notes_per_segment = total_notes / report.total_segments if report.total_segments else 0.0

    if report.total_segments > 0:
        report.citation_accuracy = ((report.total_segments - citation_failures) / report.total_segments) * 100
        report.numeric_accuracy = ((report.total_segments - numeric_failures) / report.total_segments) * 100

    report.length_flags = length_flags
    report.calque_suspects = calque_count
    report.readability_avg = sum(readability_scores) / len(readability_scores) if readability_scores else 100.0
    report.readability_below_60 = sum(1 for s in readability_scores if s < 60)
    report.repetition_flags = repetition_count
    report.informal_markers = informal_count

    if hasattr(project, "grounding") and project.grounding:
        report.tm_entries_total = len(project.grounding.termbank.items)

    return report
