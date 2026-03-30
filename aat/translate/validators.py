"""Deterministic anti-hallucination validators for translation results."""

import re
from dataclasses import dataclass, field
from typing import Any

from aat.storage.models import ValidationResult, ValidatorStatus, ValidatorIssue


@dataclass
class ValidationResult:
    """Result of a validation check."""
    status: ValidatorStatus
    issues: list[ValidatorIssue] = field(default_factory=list)

    def is_pass(self) -> bool:
        """Check if validation passed."""
        return self.status == ValidatorStatus.PASS

    def is_fail(self) -> bool:
        """Check if validation failed."""
        return self.status == ValidatorStatus.FAIL

    def is_flag(self) -> bool:
        """Check if validation has flags."""
        return self.status == ValidatorStatus.FLAG


class BaseValidator:
    """Base class for all validators."""

    def validate(self, source: str, translation: str) -> ValidationResult:
        """
        Validate translation against source text.

        Args:
            source: Original source text.
            translation: Translated text.

        Returns:
            ValidationResult with status and any issues found.
        """
        raise NotImplementedError("Subclasses must implement validate()")


class CitationPreservationValidator(BaseValidator):
    """Validates that citations are preserved exactly.

    Extracts citations from source and translation using regex
    and checks that citations match exactly (order-insensitive acceptable).
    """

    # Parenthetical citation pattern: (Author, 2020) or (Author et al., 2020)
    PARENTHETICAL_PATTERN = r"\(([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*(?:\s+et\s+al\.?)?,\s+\d{4})\)"

    # Bracketed citation pattern: [12] or [12, 13]
    BRACKETED_PATTERN = r"\[(\d+(?:,\s*\d+)*)\]"

    # Parenthetical without comma: (Author et al. 2020)
    PARENTHETICAL_NO_COMMA_PATTERN = r"\(([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*(?:\s+et\s+al\.?)?\s+\d{4})\)"

    # Full name pattern: (Smith and Johnson, 2020)
    FULL_NAME_PATTERN = r"\(([A-Z][a-z]+(?:\s+and\s+[A-Z][a-z]+)+,\s+\d{4})\)"

    def __init__(self) -> None:
        """Initialize the validator."""
        self._patterns = [
            self.PARENTHETICAL_PATTERN,
            self.PARENTHETICAL_NO_COMMA_PATTERN,
            self.FULL_NAME_PATTERN,
            self.BRACKETED_PATTERN,
        ]

    def validate(self, source: str, translation: str) -> ValidationResult:
        """
        Validate that citations are preserved.

        Args:
            source: Original source text.
            translation: Translated text.

        Returns:
            ValidationResult with any citation mismatches.
        """
        source_citations = self._extract_citations(source)
        translation_citations = self._extract_citations(translation)

        issues: list[ValidatorIssue] = []

        # Check that all source citations are in translation
        for citation in source_citations:
            if citation not in translation_citations:
                issues.append(
                    ValidatorIssue(
                        code="CITATION_MISMATCH",
                        detail=f"Citation '{citation}' not found in translation",
                        location={"citation": citation},
                    )
                )

        # Check that translation doesn't have extra citations not in source
        for citation in translation_citations:
            if citation not in source_citations:
                issues.append(
                    ValidatorIssue(
                        code="CITATION_INJECTION",
                        detail=f"Extra citation '{citation}' in translation not in source",
                        location={"citation": citation},
                    )
                )

        if issues:
            return ValidationResult(status=ValidatorStatus.FAIL, issues=issues)

        return ValidationResult(status=ValidatorStatus.PASS)

    def _extract_citations(self, text: str) -> list[str]:
        """
        Extract all citations from text.

        Args:
            text: Text to search.

        Returns:
            List of citation text strings.
        """
        citations = []

        for pattern in self._patterns:
            for match in re.finditer(pattern, text):
                citations.append(match.group())

        return citations


class NumericFidelityValidator(BaseValidator):
    """Validates that numbers are preserved exactly.

    Extracts numbers, percentages, ranges and checks
    that they match exactly between source and translation.
    """

    # Number patterns
    INTEGER_PATTERN = r"\b\d+\b"
    DECIMAL_PATTERN = r"\b\d+\.\d+\b"
    PERCENTAGE_PATTERN = r"\b\d+(?:\.\d+)?%\b"
    RANGE_PATTERN = r"\b\d+\s*-\s*\d+\b"

    # P-value patterns
    PVALUE_PATTERN = r"p\s*[<>=!]+\s*\d+(?:\.\d+)?"

    def validate(self, source: str, translation: str) -> ValidationResult:
        """
        Validate that numbers are preserved.

        Args:
            source: Original source text.
            translation: Translated text.

        Returns:
            ValidationResult with any numeric mismatches.
        """
        source_numbers = self._extract_numbers(source)
        translation_numbers = self._extract_numbers(translation)

        issues: list[ValidatorIssue] = []

        # Check that all source numbers are in translation
        for num in source_numbers:
            if num not in translation_numbers:
                issues.append(
                    ValidatorIssue(
                        code="NUMERIC_MISMATCH",
                        detail=f"Number '{num}' not found in translation",
                        location={"number": num},
                    )
                )

        # Check that translation doesn't have extra numbers
        for num in translation_numbers:
            if num not in source_numbers:
                issues.append(
                    ValidatorIssue(
                        code="NUMERIC_INJECTION",
                        detail=f"Extra number '{num}' in translation not in source",
                        location={"number": num},
                    )
                )

        if issues:
            return ValidationResult(status=ValidatorStatus.FAIL, issues=issues)

        return ValidationResult(status=ValidatorStatus.PASS)

    def _extract_numbers(self, text: str) -> list[str]:
        """
        Extract all numbers from text.

        Args:
            text: Text to search.

        Returns:
            List of number strings.
        """
        numbers = []

        # Extract p-values first
        for match in re.finditer(self.PVALUE_PATTERN, text):
            numbers.append(match.group())

        # Extract percentages
        for match in re.finditer(self.PERCENTAGE_PATTERN, text):
            numbers.append(match.group())

        # Extract ranges
        for match in re.finditer(self.RANGE_PATTERN, text):
            numbers.append(match.group())

        # Extract decimals
        for match in re.finditer(self.DECIMAL_PATTERN, text):
            numbers.append(match.group())

        # Extract integers
        for match in re.finditer(self.INTEGER_PATTERN, text):
            numbers.append(match.group())

        return numbers


class ReferenceInjectionValidator(BaseValidator):
    """Validates that no new citations are injected.

    If translation contains any citation pattern not in source → FAIL.
    This is stricter than CitationPreservationValidator as it catches
    any citation-like pattern, not just exact matches.
    """

    # Citation-like patterns (parenthetical and bracketed)
    CITATION_PATTERNS = [
        r"\(([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*(?:\s+et\s+al\.?)?,\s+\d{4})\)",
        r"\(([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*(?:\s+et\s+al\.?)?\s+\d{4})\)",
        r"\(([A-Z][a-z]+(?:\s+and\s+[A-Z][a-z]+)+,\s+\d{4})\)",
        r"\[\d+(?:,\s*\d+)*\]",
    ]

    def validate(self, source: str, translation: str) -> ValidationResult:
        """
        Validate no new citation patterns are injected.

        Args:
            source: Original source text.
            translation: Translated text.

        Returns:
            ValidationResult with any injection issues.
        """
        source_citations = self._extract_all_citation_patterns(source)
        translation_citations = self._extract_all_citation_patterns(translation)

        issues: list[ValidatorIssue] = []

        # Check for any citation pattern in translation not in source
        for citation in translation_citations:
            if citation not in source_citations:
                issues.append(
                    ValidatorIssue(
                        code="REFERENCE_INJECTION",
                        detail=f"Potential citation injection '{citation}' in translation",
                        location={"citation": citation},
                    )
                )

        if issues:
            return ValidationResult(status=ValidatorStatus.FAIL, issues=issues)

        return ValidationResult(status=ValidatorStatus.PASS)

    def _extract_all_citation_patterns(self, text: str) -> list[str]:
        """
        Extract all citation-like patterns from text.

        Args:
            text: Text to search.

        Returns:
            List of citation text strings.
        """
        citations = []

        for pattern in self.CITATION_PATTERNS:
            for match in re.finditer(pattern, text):
                citations.append(match.group())

        return citations


class LengthChangeHeuristic(BaseValidator):
    """Validates that translation length is reasonable.

    If translation length > 1.6× source length → flag (not fail).
    This is a heuristic to flag potentially bad translations.
    """

    FLAG_THRESHOLD = 1.6  # Translation is 1.6x longer than source

    def validate(self, source: str, translation: str) -> ValidationResult:
        """
        Validate that translation length is reasonable.

        Args:
            source: Original source text.
            translation: Translated text.

        Returns:
            ValidationResult with FLAG if length is excessive.
        """
        source_len = len(source) if source else 0
        translation_len = len(translation) if translation else 0

        # Avoid division by zero
        if source_len == 0:
            return ValidationResult(status=ValidatorStatus.PASS, issues=[])

        ratio = translation_len / source_len

        if ratio > self.FLAG_THRESHOLD:
            return ValidationResult(
                status=ValidatorStatus.FLAG,
                issues=[
                    ValidatorIssue(
                        code="LENGTH_EXCESSIVE",
                        detail=f"Translation length ratio {ratio:.2f} exceeds threshold {self.FLAG_THRESHOLD}",
                        location={
                            "source_length": source_len,
                            "translation_length": translation_len,
                            "ratio": ratio,
                        },
                    )
                ],
            )

        return ValidationResult(status=ValidatorStatus.PASS)


def run_all_validators(source: str, translation: str) -> list[ValidationResult]:
    """
    Run all validators on source/translation pair.

    Args:
        source: Original source text.
        translation: Translated text.

    Returns:
        List of ValidationResult objects.
    """
    validators = [
        CitationPreservationValidator(),
        NumericFidelityValidator(),
        ReferenceInjectionValidator(),
        LengthChangeHeuristic(),
    ]

    results = []
    for validator in validators:
        result = validator.validate(source, translation)
        results.append(result)

    return results


def has_any_failures(results: list[ValidationResult]) -> bool:
    """
    Check if any validator failed.

    Args:
        results: List of ValidationResult objects.

    Returns:
        True if any result has FAIL status.
    """
    return any(result.is_fail() for result in results)


class UncertaintyDetector:
    """Deterministic uncertainty detector for source text.

    Identifies ambiguous pronouns, unknown terms, figurative language,
    and temporal ambiguity that may require human attention during translation.
    """

    AMBIGUOUS_PRONOUNS = {"it", "this", "that", "they", "them", "these", "those"}
    FIGURATIVE_PHRASES = [
        "paints a picture", "tip of the iceberg", "at the end of the day",
        "sheds light", "paves the way", "opens the door", "breaks new ground",
        "plays a role", "draws on", "builds on", "lays the groundwork",
        "bridges the gap", "fills the gap", "scratches the surface",
    ]
    TEMPORAL_MARKERS = [
        "at that time", "at this point", "by then", "previously",
        "recently", "currently", "formerly", "hitherto",
    ]

    def __init__(self, min_confidence: float = 0.5) -> None:
        self.min_confidence = min_confidence

    def detect_ambiguous_references(self, text: str) -> list[dict]:
        results = []
        words = re.findall(r"\b\w+\b", text.lower())
        for word in words:
            if word in self.AMBIGUOUS_PRONOUNS:
                conf = 0.8 if word in ("it", "this", "they") else 0.6
                if conf >= self.min_confidence:
                    results.append({
                        "span": word,
                        "type": "AMBIGUOUS_REFERENCE",
                        "question": f"What does '{word}' refer to?",
                        "confidence": conf,
                    })
        return results

    def detect_unknown_terms(self, text: str) -> list[dict]:
        results = []
        for match in re.finditer(r"\b[A-Z][A-Z0-9]+-?\d+\b", text):
            term = match.group()
            results.append({
                "span": term,
                "type": "UNKNOWN_TERM",
                "question": f"What is the correct translation of '{term}'?",
                "confidence": 0.9,
            })
        for match in re.finditer(r"\b[A-Z]{3,}\b", text):
            term = match.group()
            if term not in {"THE", "AND", "FOR", "NOT", "BUT", "ARE", "WAS", "HAS"}:
                results.append({
                    "span": term,
                    "type": "UNKNOWN_TERM",
                    "question": f"Is '{term}' an acronym requiring expansion?",
                    "confidence": 0.7,
                })
        return [r for r in results if r["confidence"] >= self.min_confidence]

    def detect_figures_of_speech(self, text: str) -> list[dict]:
        results = []
        text_lower = text.lower()
        for phrase in self.FIGURATIVE_PHRASES:
            if phrase in text_lower:
                results.append({
                    "span": phrase,
                    "type": "FIGURATIVE_LANGUAGE",
                    "question": f"How should '{phrase}' be translated?",
                    "confidence": 0.75,
                })
        return [r for r in results if r["confidence"] >= self.min_confidence]

    def detect_temporal_ambiguity(self, text: str) -> list[dict]:
        results = []
        text_lower = text.lower()
        for marker in self.TEMPORAL_MARKERS:
            if marker in text_lower:
                results.append({
                    "span": marker,
                    "type": "TEMPORAL_AMBIGUITY",
                    "question": f"What time period does '{marker}' refer to?",
                    "confidence": 0.7,
                })
        return [r for r in results if r["confidence"] >= self.min_confidence]

    def detect_all(self, text: str) -> dict[str, list[dict]]:
        return {
            "ambiguous_references": self.detect_ambiguous_references(text),
            "unknown_terms": self.detect_unknown_terms(text),
            "figures_of_speech": self.detect_figures_of_speech(text),
            "temporal_ambiguity": self.detect_temporal_ambiguity(text),
        }


def has_any_flags(results: list[ValidationResult]) -> bool:
    """
    Check if any validator raised flags.

    Args:
        results: List of ValidationResult objects.

    Returns:
        True if any result has FLAG status.
    """
    return any(result.is_flag() for result in results)
