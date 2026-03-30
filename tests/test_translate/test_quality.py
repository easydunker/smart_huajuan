"""Tests for post-translation quality heuristics."""

import pytest

from aat.translate.quality import (
    AcademicToneChecker,
    CalqueDetector,
    ReadabilityScorer,
    RepetitionDetector,
    run_quality_heuristics,
)


class TestCalqueDetector:
    def test_detects_known_calque(self):
        detector = CalqueDetector()
        result = detector.check("在这个问题的光中，我们需要考虑。")
        assert not result.passed
        assert len(result.issues) >= 1
        assert any("在" in i.span and "光中" in i.span for i in result.issues)

    def test_clean_text_passes(self):
        detector = CalqueDetector()
        result = detector.check("本研究分析了语言变异现象。")
        assert result.passed
        assert len(result.issues) == 0


class TestReadabilityScorer:
    def test_overly_long_sentence_flagged(self):
        scorer = ReadabilityScorer()
        long_sentence = "这" * 100 + "。"
        result = scorer.check(long_sentence)
        assert not result.passed
        assert any("long sentence" in i.detail.lower() or "chars" in i.detail for i in result.issues)

    def test_normal_text_passes(self):
        scorer = ReadabilityScorer()
        result = scorer.check("这是一个正常的句子。这也是一个正常的句子。")
        assert result.passed
        assert result.score is not None
        assert result.score > 80

    def test_empty_text_passes(self):
        scorer = ReadabilityScorer()
        result = scorer.check("")
        assert result.passed
        assert result.score == 100.0


class TestRepetitionDetector:
    def test_repetition_flagged(self):
        detector = RepetitionDetector()
        text = "这是翻译" * 5
        result = detector.check(text)
        assert not result.passed
        assert len(result.issues) >= 1

    def test_normal_text_passes(self):
        detector = RepetitionDetector()
        result = detector.check("本研究分析了语言变异现象，发现了有趣的结果。")
        assert result.passed


class TestAcademicToneChecker:
    def test_informal_markers_detected(self):
        checker = AcademicToneChecker()
        result = checker.check("这个结果很有趣呢，让我们看看吧。")
        assert not result.passed
        markers_found = [i.span for i in result.issues]
        assert "呢" in markers_found
        assert "吧" in markers_found

    def test_formal_text_passes(self):
        checker = AcademicToneChecker()
        result = checker.check("本研究采用定量方法分析数据。")
        assert result.passed

    def test_empty_text_passes(self):
        checker = AcademicToneChecker()
        result = checker.check("")
        assert result.passed


class TestRunAllHeuristics:
    def test_clean_text_all_pass(self):
        results = run_quality_heuristics("本研究采用定量方法。结果显示显著差异。")
        assert all(r.passed for r in results)
        assert len(results) == 4

    def test_returns_all_four_heuristics(self):
        results = run_quality_heuristics("测试文本。")
        names = [r.name for r in results]
        assert "calque_detector" in names
        assert "readability_scorer" in names
        assert "repetition_detector" in names
        assert "academic_tone_checker" in names
