"""Global consistency pass: term and citation checks across all segments."""

import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from aat.parsing.citation import CitationExtractor

if TYPE_CHECKING:
    from aat.storage.models import TranslationProject, TranslationSegment
    from aat.translate.translation_memory import TranslationMemory


@dataclass
class TermInconsistency:
    """A term translated inconsistently across segments."""

    source_term: str
    translations: dict[str, list[str]]  # target_text -> list[segment_ids]
    suggested: str  # majority translation


@dataclass
class CitationIssue:
    """A citation that was dropped or injected."""

    citation_text: str
    issue_type: str  # "dropped" or "injected"
    segment_ids: list[str] = field(default_factory=list)


@dataclass
class GlobalPassReport:
    """Result of running all global consistency checks."""

    term_inconsistencies: list[TermInconsistency] = field(default_factory=list)
    citation_issues: list[CitationIssue] = field(default_factory=list)
    passed: bool = True
    summary: str = ""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ENGLISH_TERM_RE = re.compile(
    r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b"  # capitalised noun phrases
    r"|\b[A-Z]{2,}\b"  # acronyms (2+ uppercase letters)
)


def _extract_english_terms(text: str) -> list[str]:
    """Extract English noun-phrase-like terms from *source* text.

    Uses a simple heuristic: capitalised words that form short phrases,
    plus uppercase acronyms.  Stop-words are filtered out.
    """
    stop = {
        "The", "This", "That", "These", "Those", "There", "Their",
        "They", "What", "Which", "Where", "When", "While", "With",
        "From", "Into", "Over", "About", "After", "Before", "Between",
        "Under", "Through", "During", "However", "Although", "Because",
        "Since", "Also", "Both", "Each", "Every", "Some", "Many",
        "Such", "Most", "More", "Other", "Another", "First", "Second",
        "Third", "Chapter", "Section", "Figure", "Table",
        "Introduction", "Discussion", "Conclusion", "Abstract", "Methods",
        "Results", "Appendix", "Analysis", "Background", "Literature",
        "Review", "Methodology",
        "AND", "THE", "FOR", "NOT", "BUT", "ARE", "WAS", "HAS",
        "HIS", "HER", "ITS",
    }
    terms: list[str] = []
    for m in _ENGLISH_TERM_RE.finditer(text):
        term = m.group()
        if term not in stop and len(term) > 1:
            terms.append(term)
    return terms


# ---------------------------------------------------------------------------
# Checkers
# ---------------------------------------------------------------------------


class TermConsistencyChecker:
    """Flag cases where the same English term is translated differently."""

    def __init__(self, tm: "TranslationMemory | None" = None) -> None:
        self._tm = tm

    def check(
        self, segments: list["TranslationSegment"]
    ) -> list[TermInconsistency]:
        locked_segments = [s for s in segments if s.locked and s.translation]

        tm_locked: set[str] = set()
        if self._tm:
            for entry in self._tm.get_locked_terms():
                tm_locked.add(entry.source_phrase.lower())

        # term -> { chinese_translation -> [sid, …] }
        term_map: dict[str, dict[str, list[str]]] = defaultdict(
            lambda: defaultdict(list)
        )
        for seg in locked_segments:
            source = seg.segment.source_text
            translation = seg.translation or ""
            sid = seg.segment.sid
            seen_terms: set[str] = set()
            for term in _extract_english_terms(source):
                key = term.lower()
                if key in tm_locked or key in seen_terms:
                    continue
                seen_terms.add(key)
                term_map[key][translation].append(sid)

        inconsistencies: list[TermInconsistency] = []
        for term, trans_dict in term_map.items():
            if len(trans_dict) > 1:
                # Pick majority as suggestion
                suggested = max(trans_dict, key=lambda t: len(trans_dict[t]))
                inconsistencies.append(
                    TermInconsistency(
                        source_term=term,
                        translations=dict(trans_dict),
                        suggested=suggested,
                    )
                )
        return inconsistencies


class CitationConsistencyChecker:
    """Verify every citation from source appears in translation output."""

    def __init__(self) -> None:
        self._extractor = CitationExtractor()

    def check(
        self, segments: list["TranslationSegment"]
    ) -> list[CitationIssue]:
        locked_segments = [s for s in segments if s.locked and s.translation]

        source_citations: dict[str, list[str]] = defaultdict(list)
        trans_citations: dict[str, list[str]] = defaultdict(list)

        for seg in locked_segments:
            sid = seg.segment.sid
            for m in self._extractor.extract_from_text(seg.segment.source_text):
                source_citations[m.text].append(sid)
            for m in self._extractor.extract_from_text(seg.translation or ""):
                trans_citations[m.text].append(sid)

        issues: list[CitationIssue] = []

        # Dropped citations
        for cite, sids in source_citations.items():
            if cite not in trans_citations:
                issues.append(
                    CitationIssue(
                        citation_text=cite,
                        issue_type="dropped",
                        segment_ids=sids,
                    )
                )

        # Injected citations
        for cite, sids in trans_citations.items():
            if cite not in source_citations:
                issues.append(
                    CitationIssue(
                        citation_text=cite,
                        issue_type="injected",
                        segment_ids=sids,
                    )
                )

        return issues


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


class GlobalPassOrchestrator:
    """Run all global checks and produce a structured report."""

    def __init__(self, tm: "TranslationMemory | None" = None) -> None:
        self._term_checker = TermConsistencyChecker(tm=tm)
        self._citation_checker = CitationConsistencyChecker()

    def run(self, project: "TranslationProject") -> GlobalPassReport:
        segments = project.segments

        term_issues = self._term_checker.check(segments)
        citation_issues = self._citation_checker.check(segments)

        passed = len(term_issues) == 0 and len(citation_issues) == 0

        parts: list[str] = []
        if term_issues:
            parts.append(f"{len(term_issues)} term inconsistencies found")
        if citation_issues:
            dropped = sum(1 for c in citation_issues if c.issue_type == "dropped")
            injected = sum(1 for c in citation_issues if c.issue_type == "injected")
            if dropped:
                parts.append(f"{dropped} citations dropped")
            if injected:
                parts.append(f"{injected} citations injected")
        summary = "; ".join(parts) if parts else "All checks passed"

        return GlobalPassReport(
            term_inconsistencies=term_issues,
            citation_issues=citation_issues,
            passed=passed,
            summary=summary,
        )
