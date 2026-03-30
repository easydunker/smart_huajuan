"""Post-translation quality heuristics for advisory checks."""

import re
from dataclasses import dataclass, field


@dataclass
class QualityIssue:
    """A single quality issue found by a heuristic."""
    heuristic: str
    detail: str
    span: str = ""


@dataclass
class HeuristicResult:
    """Result from running a quality heuristic."""
    name: str
    passed: bool
    score: float | None = None  # 0-100 for scorers
    issues: list[QualityIssue] = field(default_factory=list)


class CalqueDetector:
    """Flags word-for-word translations that sound unnatural in Chinese."""

    CALQUE_PATTERNS = [
        (r"在[^。，、]{0,10}的光中", "in light of"),
        (r"在[^。，、]{0,10}的另一手中", "on the other hand"),
        (r"扮演[^。，、]{0,6}角色", "play a role"),
        (r"打开[^。，、]{0,6}门", "open the door"),
        (r"铺平[^。，、]{0,6}道路", "pave the way"),
        (r"在[^。，、]{0,6}的尽头", "at the end of the day"),
        (r"冰山[^。，、]{0,6}一角", "tip of the iceberg"),
        (r"抛砖引玉", None),  # Used inappropriately in academic text
        (r"带来[^。，、]{0,6}到桌上", "bring to the table"),
    ]

    def check(self, text: str) -> HeuristicResult:
        issues = []
        for pattern, english_origin in self.CALQUE_PATTERNS:
            for match in re.finditer(pattern, text):
                detail = f"Suspected calque: '{match.group()}'"
                if english_origin:
                    detail += f" (from '{english_origin}')"
                issues.append(QualityIssue(
                    heuristic="calque_detector",
                    detail=detail,
                    span=match.group(),
                ))
        return HeuristicResult(
            name="calque_detector",
            passed=len(issues) == 0,
            issues=issues,
        )


class ReadabilityScorer:
    """Estimates readability of Chinese output."""

    PUNCTUATION = set("。！？；：，、")
    MAX_CHARS_WITHOUT_PUNCTUATION = 80

    def check(self, text: str) -> HeuristicResult:
        issues = []

        sentences = re.split(r'[。！？]', text)
        sentences = [s.strip() for s in sentences if s.strip()]

        if not sentences:
            return HeuristicResult(name="readability_scorer", passed=True, score=100.0)

        total_score = 0
        for sentence in sentences:
            char_count = sum(1 for c in sentence if c not in self.PUNCTUATION)
            if char_count > self.MAX_CHARS_WITHOUT_PUNCTUATION:
                issues.append(QualityIssue(
                    heuristic="readability_scorer",
                    detail=f"Overly long sentence ({char_count} chars): '{sentence[:50]}...'",
                    span=sentence[:80],
                ))
                total_score += max(0, 100 - (char_count - self.MAX_CHARS_WITHOUT_PUNCTUATION))
            else:
                total_score += 100

        avg_score = total_score / len(sentences) if sentences else 100

        if text:
            punct_count = sum(1 for c in text if c in self.PUNCTUATION)
            punct_density = punct_count / len(text)
            if punct_density < 0.02:
                issues.append(QualityIssue(
                    heuristic="readability_scorer",
                    detail=f"Low punctuation density ({punct_density:.3f})",
                ))

        return HeuristicResult(
            name="readability_scorer",
            passed=len(issues) == 0,
            score=round(avg_score, 1),
            issues=issues,
        )


class RepetitionDetector:
    """Flags excessive repetition of the same phrase within a segment."""

    MIN_PHRASE_LENGTH = 4
    MAX_REPETITIONS = 3

    def check(self, text: str) -> HeuristicResult:
        issues = []

        phrase_counts: dict[str, int] = {}
        for n in range(self.MIN_PHRASE_LENGTH, 9):
            for i in range(len(text) - n + 1):
                phrase = text[i:i+n]
                if any(c in "。！？；：，、\n\r\t " for c in phrase):
                    continue
                phrase_counts[phrase] = phrase_counts.get(phrase, 0) + 1

        flagged: set[str] = set()
        for phrase, count in sorted(phrase_counts.items(), key=lambda x: -len(x[0])):
            if count > self.MAX_REPETITIONS:
                if not any(phrase in f for f in flagged):
                    flagged.add(phrase)
                    issues.append(QualityIssue(
                        heuristic="repetition_detector",
                        detail=f"Phrase '{phrase}' repeated {count} times",
                        span=phrase,
                    ))

        return HeuristicResult(
            name="repetition_detector",
            passed=len(issues) == 0,
            issues=issues,
        )


class AcademicToneChecker:
    """Flags informal markers that shouldn't appear in academic Chinese."""

    INFORMAL_MARKERS = [
        "了吧", "呢", "啊", "嘛", "哦", "呀", "吧", "哈", "嗯",
        "哎", "哟", "喔", "嘿", "唉",
    ]

    def check(self, text: str) -> HeuristicResult:
        issues = []
        for marker in self.INFORMAL_MARKERS:
            count = text.count(marker)
            if count > 0:
                issues.append(QualityIssue(
                    heuristic="academic_tone_checker",
                    detail=f"Informal marker '{marker}' found {count} time(s)",
                    span=marker,
                ))
        return HeuristicResult(
            name="academic_tone_checker",
            passed=len(issues) == 0,
            issues=issues,
        )


def run_quality_heuristics(text: str) -> list[HeuristicResult]:
    """Run all quality heuristics on translated text.

    Args:
        text: The translated Chinese text.

    Returns:
        List of HeuristicResult from each checker.
    """
    heuristics = [
        CalqueDetector(),
        ReadabilityScorer(),
        RepetitionDetector(),
        AcademicToneChecker(),
    ]
    return [h.check(text) for h in heuristics]
