"""Citation extraction and normalization utilities."""

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from aat.storage.models import Citation

if TYPE_CHECKING:
    from docx.paragraph import Paragraph


@dataclass
class CitationMatch:
    """Represents a matched citation in text."""
    text: str
    start: int
    end: int


class CitationExtractor:
    """Extract citations from text using multiple patterns."""

    # Parenthetical citation pattern: (Author, 2020) or (Author et al., 2020)
    PARENTHETICAL_PATTERN = r"\(([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*(?:\s+et\s+al\.?)?,\s+\d{4})\)"

    # Bracketed citation pattern: [12] or [12, 13]
    BRACKETED_PATTERN = r"\[(\d+(?:,\s*\d+)*)\]"

    # Parenthetical without comma: (Author et al. 2020)
    PARENTHETICAL_NO_COMMA_PATTERN = r"\(([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*(?:\s+et\s+al\.?)?\s+\d{4})\)"

    # Full name pattern: (Smith and Johnson, 2020)
    FULL_NAME_PATTERN = r"\(([A-Z][a-z]+(?:\s+and\s+[A-Z][a-z]+)+,\s+\d{4})\)"

    def __init__(self) -> None:
        """Initialize the citation extractor."""
        self._patterns = [
            self.PARENTHETICAL_PATTERN,
            self.PARENTHETICAL_NO_COMMA_PATTERN,
            self.FULL_NAME_PATTERN,
            self.BRACKETED_PATTERN,
        ]

    def extract_from_text(self, text: str) -> list[CitationMatch]:
        """
        Extract all citations from text.

        Args:
            text: Text to search for citations.

        Returns:
            List of CitationMatch objects, sorted by start position.
        """
        matches = []

        for pattern in self._patterns:
            for match in re.finditer(pattern, text):
                matches.append(
                    CitationMatch(
                        text=match.group(),
                        start=match.start(),
                        end=match.end(),
                    )
                )

        # Sort by start position
        matches.sort(key=lambda m: m.start)

        return matches

    def is_citation(self, text: str) -> bool:
        """
        Check if text is a valid citation.

        Args:
            text: Text to check.

        Returns:
            True if text matches a citation pattern.
        """
        text = text.strip()

        # Check each pattern
        patterns = [
            self.PARENTHETICAL_PATTERN,
            self.BRACKETED_PATTERN,
            self.PARENTHETICAL_NO_COMMA_PATTERN,
            self.FULL_NAME_PATTERN,
        ]

        for pattern in patterns:
            if re.fullmatch(pattern, text):
                return True

        return False

    def normalize(self, citation_text: str) -> str:
        """
        Normalize citation text for consistency.

        Standardizes:
        - Multiple spaces to single space
        - "et. al." to "et al."
        - "et. al" to "et al."
        - "et al" to "et al."

        Args:
            citation_text: Text to normalize.

        Returns:
            Normalized citation text.
        """
        text = citation_text.strip()

        # Normalize "et al." variations to "et al."
        # Match "et" followed by optional dots/spaces, "al", optional dots
        # Ensure there's a space after "et al." if followed by word characters
        text = re.sub(
            r"\bet\s*\.?\s*al\s*\.?",
            "et al. ",
            text,
            flags=re.IGNORECASE,
        )

        # Normalize spacing globally
        text = re.sub(r"\s+", " ", text)

        # Strip trailing space
        text = text.strip()

        return text

    def extract_authors(self, citation_text: str) -> list[str]:
        """
        Extract author names from a citation.

        Args:
            citation_text: Citation text.

        Returns:
            List of author names.
        """
        authors = []

        # Parenthetical citations
        parenthetical_match = re.match(r"\((.*?)\)", citation_text)
        if parenthetical_match:
            inner = parenthetical_match.group(1)

            # Check for "et al." pattern
            if "et al." in inner.lower():
                # Extract author before "et al."
                author_part = inner.split("et al")[0].strip()
                # Remove comma and year
                author_part = re.sub(r",?\s*\d{4}", "", author_part).strip()
                if author_part:
                    authors.append(author_part)
            elif re.search(r"\d{4}$", inner):
                # Remove year
                author_part = re.sub(r",?\s*\d{4}$", "", inner).strip()
                if " and " in author_part:
                    authors.extend([a.strip() for a in author_part.split(" and ")])
                else:
                    authors.append(author_part)

        # Bracketed citations don't have author names
        elif citation_text.startswith("["):
            return []

        return authors

    def extract_year(self, citation_text: str) -> str | None:
        """
        Extract year from a citation.

        Args:
            citation_text: Citation text.

        Returns:
            Year string or None if not found.
        """
        # Look for 4-digit year
        year_match = re.search(r"\b(19|20)\d{2}\b", citation_text)
        if year_match:
            return year_match.group()
        return None

    def get_citation_type(self, citation_text: str) -> str:
        """
        Determine the citation type.

        Returns:
            Type string: 'parenthetical', 'bracketed', or 'unknown'.
        """
        text = citation_text.strip()

        if text.startswith("[") and text.endswith("]"):
            return "bracketed"
        elif text.startswith("(") and text.endswith(")"):
            return "parenthetical"
        else:
            return "unknown"


def count_citations(text: str) -> int:
    """
    Count the number of citations in text.

    Args:
        text: Text to count citations in.

    Returns:
        Number of citations found.
    """
    extractor = CitationExtractor()
    matches = extractor.extract_from_text(text)
    return len(matches)


def find_citations(text: str) -> list[str]:
    """
    Find all citation texts in text.

    Args:
        text: Text to search.

    Returns:
        List of citation text strings.
    """
    extractor = CitationExtractor()
    matches = extractor.extract_from_text(text)
    return [m.text for m in matches]
