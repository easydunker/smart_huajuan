"""Tests for citation extraction."""

import pytest
from hypothesis import given, strategies as st

from aat.parsing.citation import (
    CitationExtractor,
    count_citations,
    find_citations,
)


class CitationTextStrategy:
    """Strategy for generating citation texts."""

    @staticmethod
    def parenthetical():
        """Generate parenthical citations."""
        return st.builds(
            lambda author, year: f"({author}, {year})",
            author=st.sampled_from([
                "Smith",
                "Johnson",
                "Brown",
                "Williams",
                "Miller",
                "Smith et al.",
                "Johnson et al.",
            ]),
            year=st.sampled_from([str(y) for y in range(1990, 2025)]),
        )

    @staticmethod
    def bracketed():
        """Generate bracketed citations."""
        return st.builds(
            lambda nums: f"[{', '.join(map(str, nums))}]",
            nums=st.lists(
                st.integers(min_value=1, max_value=999),
                min_size=1,
                max_size=5,
            ),
        )

    @staticmethod
    def citation():
        """Generate any citation."""
        return st.one_of(
            CitationTextStrategy.parenthetical(),
            CitationTextStrategy.bracketed(),
        )


class TestCitationExtractor:
    """Test CitationExtractor."""

    def test_extract_parenthetical_citation(self) -> None:
        """Test extracting (Smith, 2020) pattern."""
        extractor = CitationExtractor()
        text = "This is a citation (Smith, 2020) in text."
        matches = extractor.extract_from_text(text)

        assert len(matches) == 1
        assert matches[0].text == "(Smith, 2020)"
        assert matches[0].start == 19

    def test_extract_multiple_citations(self) -> None:
        """Test extracting multiple citations."""
        extractor = CitationExtractor()
        text = "Studies (Smith, 2020) and (Johnson, 2021) show results."
        matches = extractor.extract_from_text(text)

        assert len(matches) == 2
        assert matches[0].text == "(Smith, 2020)"
        assert matches[1].text == "(Johnson, 2021)"

    def test_extract_et_al_citation(self) -> None:
        """Test extracting (Smith et al., 2020) pattern."""
        extractor = CitationExtractor()
        text = "This work (Smith et al., 2020) demonstrates..."
        matches = extractor.extract_from_text(text)

        assert len(matches) == 1
        assert matches[0].text == "(Smith et al., 2020)"

    def test_extract_bracketed_citation(self) -> None:
        """Test extracting [12] pattern."""
        extractor = CitationExtractor()
        text = "Multiple studies [1, 2, 3] support this."
        matches = extractor.extract_from_text(text)

        assert len(matches) == 1
        assert matches[0].text == "[1, 2, 3]"

    def test_extract_without_comma(self) -> None:
        """Test extracting (Brown et al. 2021) without comma."""
        extractor = CitationExtractor()
        text = "Recent work (Brown et al. 2021) demonstrates this."
        matches = extractor.extract_from_text(text)

        assert len(matches) == 1
        assert matches[0].text == "(Brown et al. 2021)"

    def test_extract_full_name_citation(self) -> None:
        """Test extracting (Smith and Johnson, 2020) pattern."""
        extractor = CitationExtractor()
        text = "Research by (Smith and Johnson, 2020) shows..."
        matches = extractor.extract_from_text(text)

        assert len(matches) == 1
        assert matches[0].text == "(Smith and Johnson, 2020)"

    def test_no_citations(self) -> None:
        """Test text without citations."""
        extractor = CitationExtractor()
        text = "This is just plain text without any citations."
        matches = extractor.extract_from_text(text)

        assert len(matches) == 0

    def test_is_citation_parenthetical(self) -> None:
        """Test is_citation for parenthetical format."""
        extractor = CitationExtractor()
        assert extractor.is_citation("(Smith, 2020)")
        assert extractor.is_citation("(Smith et al., 2020)")

    def test_is_citation_bracketed(self) -> None:
        """Test is_citation for bracketed format."""
        extractor = CitationExtractor()
        assert extractor.is_citation("[12]")
        assert extractor.is_citation("[1, 2, 3]")

    def test_is_citation_false(self) -> None:
        """Test is_citation returns false for non-citations."""
        extractor = CitationExtractor()
        assert not extractor.is_citation("Smith 2020")
        assert not extractor.is_citation("(Smith)")
        assert not extractor.is_citation("text")
        assert not extractor.is_citation("(Smith, abc)")

    def test_normalize_spacing(self) -> None:
        """Test citation normalization with spacing."""
        extractor = CitationExtractor()
        normalized = extractor.normalize("(Smith,    2020)")
        assert normalized == "(Smith, 2020)"

    def test_normalize_et_al(self) -> None:
        """Test citation normalization of et al."""
        extractor = CitationExtractor()

        # Various "et al." forms
        assert extractor.normalize("(Smith et al 2020)") == "(Smith et al. 2020)"
        assert extractor.normalize("(Smith et.al. 2020)") == "(Smith et al. 2020)"
        assert extractor.normalize("(Smith et.al 2020)") == "(Smith et al. 2020)"

    def test_extract_authors_simple(self) -> None:
        """Test extracting simple author name."""
        extractor = CitationExtractor()
        authors = extractor.extract_authors("(Smith, 2020)")
        assert authors == ["Smith"]

    def test_extract_authors_et_al(self) -> None:
        """Test extracting author from et al. citation."""
        extractor = CitationExtractor()
        authors = extractor.extract_authors("(Smith et al., 2020)")
        assert authors == ["Smith"]

    def test_extract_authors_multiple(self) -> None:
        """Test extracting multiple authors."""
        extractor = CitationExtractor()
        authors = extractor.extract_authors("(Smith and Johnson, 2020)")
        assert "Smith" in authors
        assert "Johnson" in authors

    def test_extract_authors_bracketed(self) -> None:
        """Test that bracketed citations have no authors."""
        extractor = CitationExtractor()
        authors = extractor.extract_authors("[12]")
        assert authors == []

    def test_extract_year(self) -> None:
        """Test extracting year from citation."""
        extractor = CitationExtractor()
        assert extractor.extract_year("(Smith, 2020)") == "2020"
        assert extractor.extract_year("(Smith et al., 2021)") == "2021"

    def test_extract_year_none(self) -> None:
        """Test extracting year when none exists."""
        extractor = CitationExtractor()
        assert extractor.extract_year("[12]") is None
        assert extractor.extract_year("(Smith)") is None

    def test_get_citation_type(self) -> None:
        """Test getting citation type."""
        extractor = CitationExtractor()
        assert extractor.get_citation_type("(Smith, 2020)") == "parenthetical"
        assert extractor.get_citation_type("[12]") == "bracketed"
        assert extractor.get_citation_type("text") == "unknown"


class TestCitationHelpers:
    """Test helper functions."""

    def test_count_citations(self) -> None:
        """Test counting citations in text."""
        text = "Studies (Smith, 2020) and (Johnson, 2021) [1, 2] show results."
        assert count_citations(text) == 3

    def test_count_no_citations(self) -> None:
        """Test counting when no citations exist."""
        assert count_citations("Plain text.") == 0

    def test_find_citations(self) -> None:
        """Test finding all citations."""
        text = "Studies (Smith, 2020) and (Johnson, 2021) show results."
        citations = find_citations(text)
        assert "(Smith, 2020)" in citations
        assert "(Johnson, 2021)" in citations


class TestCitationPropertyTests:
    """Property-based tests for citation handling."""

    @given(citation_text=CitationTextStrategy.citation())
    def test_extracted_matches_pattern(self, citation_text: str) -> None:
        """Test that extracted citations match the pattern."""
        extractor = CitationExtractor()
        assert extractor.is_citation(citation_text)

    @given(
        text=st.text(alphabet=st.characters(whitelist_categories="L", max_codepoint=127))
    )
    def test_count_is_non_negative(self, text: str) -> None:
        """Test that citation count is always non-negative."""
        n = count_citations(text)
        assert n >= 0

    @given(
        text=st.text(alphabet=st.characters(whitelist_categories="L", max_codepoint=127))
    )
    def test_find_returns_count(self, text: str) -> None:
        """Test that find() returns same number as count()."""
        found = len(find_citations(text))
        counted = count_citations(text)
        assert found == counted

    @given(citation_text=CitationTextStrategy.citation())
    def test_normalize_preserves_type(self, citation_text: str) -> None:
        """Test that normalization preserves citation type."""
        extractor = CitationExtractor()
        original_type = extractor.get_citation_type(citation_text)
        normalized = extractor.normalize(citation_text)
        normalized_type = extractor.get_citation_type(normalized)
        assert original_type == normalized_type

    @given(citation_text=CitationTextStrategy.parenthetical())
    def test_parenthetical_has_year(self, citation_text: str) -> None:
        """Test that parenthetical citations have years."""
        extractor = CitationExtractor()
        year = extractor.extract_year(citation_text)
        assert year is not None
        assert year.isdigit()
        assert len(year) == 4

    @given(citation_text=CitationTextStrategy.bracketed())
    def test_bracketed_has_no_year(self, citation_text: str) -> None:
        """Test that bracketed citations don't have years."""
        extractor = CitationExtractor()
        year = extractor.extract_year(citation_text)
        assert year is None

    @given(citation_text=CitationTextStrategy.bracketed())
    def test_bracketed_has_no_authors(self, citation_text: str) -> None:
        """Test that bracketed citations don't have authors."""
        extractor = CitationExtractor()
        authors = extractor.extract_authors(citation_text)
        assert authors == []
