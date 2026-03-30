"""Tests for translation validators."""

import hypothesis
from hypothesis import given, strategies as st, settings

from aat.translate.validators import (
    CitationPreservationValidator,
    LengthChangeHeuristic,
    NumericFidelityValidator,
    ReferenceInjectionValidator,
    has_any_failures,
    has_any_flags,
    run_all_validators,
)


class TestCitationPreservationValidator:
    """Test CitationPreservationValidator."""

    def test_exact_match_passes(self) -> None:
        """Test that exact citation match passes."""
        validator = CitationPreservationValidator()
        source = "This is (Smith, 2020) a test."
        translation = "这是 (Smith, 2020) 一个测试。"

        result = validator.validate(source, translation)
        assert result.is_pass()

    def test_missing_citation_fails(self) -> None:
        """Test that missing citation fails."""
        validator = CitationPreservationValidator()
        source = "This is (Smith, 2020) a test."
        translation = "这是 一个测试。"  # Citation missing

        result = validator.validate(source, translation)
        assert result.is_fail()
        assert len(result.issues) == 1
        assert result.issues[0].code == "CITATION_MISMATCH"

    def test_multiple_citations(self) -> None:
        """Test with multiple citations."""
        validator = CitationPreservationValidator()
        source = "Citation one (Smith, 2020) and two (Johnson, 2021)."
        translation = "引用一 (Smith, 2020) 和二 (Johnson, 2021)。"

        result = validator.validate(source, translation)
        assert result.is_pass()

    def test_bracketed_citations(self) -> None:
        """Test bracketed citation format."""
        validator = CitationPreservationValidator()
        source = "Studies [1, 2, 3] support this."
        translation = "研究 [1, 2, 3] 支持这一点。"

        result = validator.validate(source, translation)
        assert result.is_pass()


class TestNumericFidelityValidator:
    """Test NumericFidelityValidator."""

    def test_exact_number_match_passes(self) -> None:
        """Test that exact number match passes."""
        validator = NumericFidelityValidator()
        source = "The p-value is p < 0.05."
        translation = "p值是 p < 0.05。"

        result = validator.validate(source, translation)
        assert result.is_pass()

    def test_missing_number_fails(self) -> None:
        """Test that missing number fails."""
        validator = NumericFidelityValidator()
        source = "The p-value is p < 0.05."
        translation = "p值是 p。"  # Number missing

        result = validator.validate(source, translation)
        assert result.is_fail()
        assert result.issues[0].code == "NUMERIC_MISMATCH"

    def test_percentage_preservation(self) -> None:
        """Test that percentages are preserved."""
        validator = NumericFidelityValidator()
        source = "Response rate was 87.5%."
        translation = "响应率是 87.5%。"

        result = validator.validate(source, translation)
        assert result.is_pass()

    def test_range_preservation(self) -> None:
        """Test that ranges are preserved."""
        validator = NumericFidelityValidator()
        source = "Age range was 18-65 years."
        translation = "年龄范围是 18-65 岁。"

        result = validator.validate(source, translation)
        assert result.is_pass()

    def test_decimal_preservation(self) -> None:
        """Test that decimals are preserved."""
        validator = NumericFidelityValidator()
        source = "Mean was 3.14159."
        translation = "均值是 3.14159。"

        result = validator.validate(source, translation)
        assert result.is_pass()


class TestReferenceInjectionValidator:
    """Test ReferenceInjectionValidator."""

    def test_no_extra_citations_passes(self) -> None:
        """Test that no extra citation patterns passes."""
        validator = ReferenceInjectionValidator()
        source = "This is (Smith, 2020) a test."
        translation = "这是 (Smith, 2020) 一个测试。"

        result = validator.validate(source, translation)
        assert result.is_pass()

    def test_extra_bracketed_citation_fails(self) -> None:
        """Test that extra bracketed citation fails."""
        validator = ReferenceInjectionValidator()
        source = "This is a test."
        translation = "这是测试 [123]。"  # Extra citation added

        result = validator.validate(source, translation)
        assert result.is_fail()
        assert result.issues[0].code == "REFERENCE_INJECTION"


class TestLengthChangeHeuristic:
    """Test LengthChangeHeuristic."""

    def test_normal_length_passes(self) -> None:
        """Test that normal length passes."""
        validator = LengthChangeHeuristic()
        source = "This is a test paragraph."
        translation = "这是一个测试段落。"

        result = validator.validate(source, translation)
        assert result.is_pass()

    def test_excessive_length_flags(self) -> None:
        """Test that excessive length flags."""
        validator = LengthChangeHeuristic()
        source = "Short text."
        translation = "这是一个很长的翻译文本，长度远超原始文本的1.6倍阈值。" * 10

        result = validator.validate(source, translation)
        assert result.is_flag()
        assert result.issues[0].code == "LENGTH_EXCESSIVE"

    def test_empty_source_passes(self) -> None:
        """Test that empty source passes."""
        validator = LengthChangeHeuristic()
        source = ""
        translation = "翻译。"

        result = validator.validate(source, translation)
        assert result.is_pass()


class TestRunAllValidators:
    """Test run_all_validators function."""

    def test_run_all_validators(self) -> None:
        source = "This is (Smith, 2020) with p < 0.05."
        translation = "这是 (Smith, 2020) 和 p < 0.05。"

        results = run_all_validators(source, translation)

        # Should have results from all validators
        assert len(results) == 4

        # All should pass
        assert all(result.is_pass() for result in results)

    def test_with_failure(self) -> None:
        source = "This is (Smith, 2020) with p < 0.05."
        translation = "这是翻译。"  # Missing citation and number

        results = run_all_validators(source, translation)

        # Should detect failures
        assert has_any_failures(results)

    def test_has_any_failures(self) -> None:
        """Test has_any_failures helper."""
        results = run_all_validators("Test (Smith, 2020).", "Translation.")

        assert has_any_failures(results)

    def test_has_any_flags(self) -> None:
        """Test has_any_flags helper."""
        source = "Short."
        translation = "Long" * 10

        results = run_all_validators(source, translation)

        # LengthChangeHeuristic should flag
        assert has_any_flags(results)


class TestCitationPropertyTests:
    """Property-based tests for citation preservation."""

    @settings(max_examples=30)
    @given(
        text=st.text(
            alphabet=st.characters(whitelist_categories="L", max_codepoint=127),
            min_size=10,
            max_size=200,
        )
    )
    def test_citation_extraction_returns_list(self, text: str) -> None:
        """Property: citation extraction always returns list."""
        validator = CitationPreservationValidator()
        citations = validator._extract_citations(text)
        assert isinstance(citations, list)

    @settings(max_examples=20)
    @given(
        text=st.text(
            alphabet=st.characters(whitelist_categories="L", max_codepoint=127),
            min_size=10,
            max_size=200,
        )
    )
    def test_extraction_non_negative(self, text: str) -> None:
        """Property: citation count is non-negative."""
        validator = CitationPreservationValidator()
        citations = validator._extract_citations(text)
        assert len(citations) >= 0


class TestNumericPropertyTests:
    """Property-based tests for numeric fidelity."""

    @settings(max_examples=30)
    @given(
        text=st.text(
            alphabet=st.characters(whitelist_categories="L", max_codepoint=127),
            min_size=10,
            max_size=200,
        )
    )
    def test_number_extraction_returns_list(self, text: str) -> None:
        """Property: number extraction always returns list."""
        validator = NumericFidelityValidator()
        numbers = validator._extract_numbers(text)
        assert isinstance(numbers, list)

    @settings(max_examples=20)
    @given(
        text=st.text(
            alphabet=st.characters(whitelist_categories="L", max_codepoint=127),
            min_size=10,
            max_size=200,
        )
    )
    def test_extraction_non_negative(self, text: str) -> None:
        """Property: number count is non-negative."""
        validator = NumericFidelityValidator()
        numbers = validator._extract_numbers(text)
        assert len(numbers) >= 0


class TestLengthPropertyTests:
    """Property-based tests for length heuristic."""

    @given(
        source=st.text(
            alphabet=st.characters(whitelist_categories="L", max_codepoint=127),
            min_size=10,
            max_size=200,
        ),
        translation=st.text(
            alphabet=st.characters(whitelist_categories="L", max_codepoint=127),
            min_size=10,
            max_size=500,
        ),
    )
    def test_result_always_has_status(
        self, source: str, translation: str
    ) -> None:
        """Property: validation result always has status."""
        validator = LengthChangeHeuristic()
        result = validator.validate(source, translation)
        assert result.status in ["PASS", "FAIL", "FLAG"]

    @given(
        source=st.text(
            alphabet=st.characters(whitelist_categories="L", max_codepoint=127),
            min_size=10,
            max_size=200,
        ),
        translation=st.text(
            alphabet=st.characters(whitelist_categories="L", max_codepoint=127),
            min_size=10,
            max_size=500,
        ),
    )
    def test_issues_is_always_list(
        self, source: str, translation: str
    ) -> None:
        """Property: issues is always a list."""
        validator = LengthChangeHeuristic()
        result = validator.validate(source, translation)
        assert isinstance(result.issues, list)
