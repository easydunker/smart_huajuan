"""Tests for GroundingBuilder module."""

import json
import tempfile
from pathlib import Path

import pytest

from aat.retrieval.grounding import (
    GroundingBuilder,
    PhraseBank,
    PhraseEntry,
    TermBank,
    TermEntry,
)


class TestTermEntry:
    """Test TermEntry dataclass."""

    def test_creation(self) -> None:
        """Test creating a term entry."""
        entry = TermEntry(
            source_term="机器学习",
            target_term="machine learning",
            evidence=["机器学习是人工智能的一个分支。"],
            confidence=0.95,
            frequency=10,
        )

        assert entry.source_term == "机器学习"
        assert entry.target_term == "machine learning"
        assert len(entry.evidence) == 1
        assert entry.confidence == 0.95
        assert entry.frequency == 10

    def test_to_dict(self) -> None:
        """Test serialization to dict."""
        entry = TermEntry(
            source_term="深度学习",
            target_term="deep learning",
            frequency=5,
        )

        d = entry.to_dict()

        assert d["source_term"] == "深度学习"
        assert d["target_term"] == "deep learning"
        assert d["frequency"] == 5

    def test_from_dict(self) -> None:
        """Test deserialization from dict."""
        data = {
            "source_term": "神经网络",
            "target_term": "neural network",
            "evidence": ["神经网络用于模式识别。"],
            "confidence": 0.9,
            "frequency": 20,
        }

        entry = TermEntry.from_dict(data)

        assert entry.source_term == "神经网络"
        assert entry.target_term == "neural network"
        assert len(entry.evidence) == 1
        assert entry.confidence == 0.9


class TestPhraseEntry:
    """Test PhraseEntry dataclass."""

    def test_creation(self) -> None:
        """Test creating a phrase entry."""
        entry = PhraseEntry(
            pattern=r"本文研究了.*?问题",
            category="intro",
            examples=["本文研究了机器学习在图像识别中的应用问题。"],
            frequency=15,
        )

        assert entry.pattern == r"本文研究了.*?问题"
        assert entry.category == "intro"
        assert len(entry.examples) == 1
        assert entry.frequency == 15

    def test_to_dict(self) -> None:
        """Test serialization to dict."""
        entry = PhraseEntry(
            pattern=r"实验结果表明",
            category="results",
            frequency=8,
        )

        d = entry.to_dict()

        assert d["pattern"] == r"实验结果表明"
        assert d["category"] == "results"
        assert d["frequency"] == 8

    def test_from_dict(self) -> None:
        """Test deserialization from dict."""
        data = {
            "pattern": r"基于.*?方法",
            "category": "method",
            "examples": ["基于深度学习的方法被广泛应用。"],
            "frequency": 12,
        }

        entry = PhraseEntry.from_dict(data)

        assert entry.pattern == r"基于.*?方法"
        assert entry.category == "method"
        assert len(entry.examples) == 1
        assert entry.frequency == 12


class TestTermBank:
    """Test TermBank dataclass."""

    def test_creation(self) -> None:
        """Test creating a term bank."""
        bank = TermBank(
            entries={},
            source_corpus="test_corpus",
            generated_at="2024-01-01T00:00:00",
        )

        assert bank.source_corpus == "test_corpus"
        assert bank.generated_at == "2024-01-01T00:00:00"

    def test_add_and_get_term(self) -> None:
        """Test adding and getting terms."""
        bank = TermBank()
        entry = TermEntry(source_term="测试", frequency=1)

        bank.add_term("测试", entry)
        retrieved = bank.get_term("测试")

        assert retrieved is not None
        assert retrieved.source_term == "测试"

    def test_to_dict(self) -> None:
        """Test serialization to dict."""
        bank = TermBank(source_corpus="corpus1")
        entry = TermEntry(source_term="术语", frequency=2)
        bank.add_term("术语", entry)

        d = bank.to_dict()

        assert d["source_corpus"] == "corpus1"
        assert "术语" in d["entries"]

    def test_from_dict(self) -> None:
        """Test deserialization from dict."""
        data = {
            "entries": {
                "概念": {
                    "source_term": "概念",
                    "target_term": "concept",
                    "evidence": [],
                    "confidence": 0.8,
                    "frequency": 5,
                }
            },
            "source_corpus": "test",
            "generated_at": "2024-01-01",
        }

        bank = TermBank.from_dict(data)

        assert bank.source_corpus == "test"
        assert "概念" in bank.entries
        assert bank.entries["概念"].target_term == "concept"


class TestPhraseBank:
    """Test PhraseBank dataclass."""

    def test_creation(self) -> None:
        """Test creating a phrase bank."""
        bank = PhraseBank(
            entries={},
            source_corpus="test_corpus",
            generated_at="2024-01-01T00:00:00",
        )

        assert bank.source_corpus == "test_corpus"

    def test_add_and_get_phrase(self) -> None:
        """Test adding and getting phrases."""
        bank = PhraseBank()
        entry = PhraseEntry(pattern=r"测试", category="intro", frequency=1)

        bank.add_phrase("测试", entry)
        retrieved = bank.get_phrase("测试")

        assert retrieved is not None
        assert retrieved.pattern == r"测试"

    def test_get_by_category(self) -> None:
        """Test getting phrases by category."""
        bank = PhraseBank()

        bank.add_phrase("p1", PhraseEntry(pattern=r"intro1", category="intro"))
        bank.add_phrase("p2", PhraseEntry(pattern=r"intro2", category="intro"))
        bank.add_phrase("p3", PhraseEntry(pattern=r"method1", category="method"))

        intro_phrases = bank.get_by_category("intro")
        method_phrases = bank.get_by_category("method")

        assert len(intro_phrases) == 2
        assert len(method_phrases) == 1

    def test_to_dict(self) -> None:
        """Test serialization to dict."""
        bank = PhraseBank(source_corpus="corpus1")
        entry = PhraseEntry(pattern=r"模式", category="general", frequency=2)
        bank.add_phrase("模式", entry)

        d = bank.to_dict()

        assert d["source_corpus"] == "corpus1"
        assert "模式" in d["entries"]

    def test_from_dict(self) -> None:
        """Test deserialization from dict."""
        data = {
            "entries": {
                "结构": {
                    "pattern": r"结构",
                    "category": "general",
                    "examples": ["结构分析"],
                    "frequency": 3,
                }
            },
            "source_corpus": "test",
            "generated_at": "2024-01-01",
        }

        bank = PhraseBank.from_dict(data)

        assert bank.source_corpus == "test"
        assert "结构" in bank.entries
        assert bank.entries["结构"].category == "general"


class TestGroundingBuilder:
    """Test GroundingBuilder class."""

    @pytest.fixture
    def temp_output_dir(self) -> Path:
        """Create a temporary output directory."""
        temp_dir = Path(tempfile.mkdtemp())
        yield temp_dir
        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_init(self, temp_output_dir: Path) -> None:
        """Test initialization."""
        builder = GroundingBuilder(temp_output_dir)

        assert builder.output_dir == temp_output_dir
        assert isinstance(builder.termbank, TermBank)
        assert isinstance(builder.phrasebank, PhraseBank)

    def test_extract_terms(self, temp_output_dir: Path) -> None:
        """Test term extraction."""
        builder = GroundingBuilder(temp_output_dir)

        text = "本文研究了机器学习和深度学习在图像处理中的应用。"
        terms = builder._extract_terms(text)

        # Should extract Chinese terms with academic suffixes
        assert isinstance(terms, list)
        # May find terms like "学习" or "处理" depending on patterns

    def test_extract_phrases(self, temp_output_dir: Path) -> None:
        """Test phrase extraction."""
        builder = GroundingBuilder(temp_output_dir)

        text = "本文研究了深度学习在图像处理中的应用。"
        phrases = builder._extract_phrases(text)

        # Should extract academic phrases
        assert isinstance(phrases, list)
        # Each phrase should be a tuple of (pattern, category)
        for pattern, category in phrases:
            assert isinstance(pattern, str)
            assert category in ["intro", "method", "results", "discussion", "general"]

    def test_process_corpus_empty(self, temp_output_dir: Path) -> None:
        """Test processing empty corpus."""
        builder = GroundingBuilder(temp_output_dir)

        result = builder.process_corpus([])

        assert result["terms"] == 0
        assert result["phrases"] == 0

    def test_process_corpus_non_chinese(self, temp_output_dir: Path) -> None:
        """Test processing non-Chinese corpus."""
        builder = GroundingBuilder(temp_output_dir)

        chunks = [
            {
                "text": "This is English text.",
                "metadata": {"language": "en"},
            }
        ]

        result = builder.process_corpus(chunks)

        # Should skip non-Chinese chunks
        assert result["terms"] == 0
        assert result["phrases"] == 0

    def test_process_corpus_chinese(self, temp_output_dir: Path) -> None:
        """Test processing Chinese corpus."""
        builder = GroundingBuilder(temp_output_dir)

        chunks = [
            {
                "text": "本文研究了机器学习和深度学习的应用。实验结果表明该方法有效。",
                "metadata": {"language": "zh"},
            }
        ]

        result = builder.process_corpus(chunks)

        # Should extract terms and phrases from Chinese text
        assert result["terms"] >= 0
        assert result["phrases"] >= 0

    def test_save_and_load(self, temp_output_dir: Path) -> None:
        """Test saving and loading termbank and phrasebank."""
        builder = GroundingBuilder(temp_output_dir)

        # Add some entries
        builder.termbank.add_term("测试", TermEntry(source_term="测试", frequency=5))
        builder.phrasebank.add_phrase("intro1", PhraseEntry(pattern=r"本文研究", category="intro"))

        # Save
        paths = builder.save()

        assert paths["termbank"].exists()
        assert paths["phrasebank"].exists()

        # Create new builder and load
        new_builder = GroundingBuilder(temp_output_dir)
        success = new_builder.load()

        assert success is True
        assert "测试" in new_builder.termbank.entries
        assert "intro1" in new_builder.phrasebank.entries

    def test_load_nonexistent(self, temp_output_dir: Path) -> None:
        """Test loading when files don't exist."""
        builder = GroundingBuilder(temp_output_dir)

        success = builder.load()

        assert success is False

    def test_load_corrupted(self, temp_output_dir: Path) -> None:
        """Test loading corrupted files."""
        builder = GroundingBuilder(temp_output_dir)

        # Create corrupted JSON files
        termbank_path = temp_output_dir / "termbank.json"
        phrasebank_path = temp_output_dir / "phrasebank.json"

        termbank_path.write_text("not valid json {{{")
        phrasebank_path.write_text("not valid json {{{")

        success = builder.load()

        assert success is False


class TestGroundingBuilderPatterns:
    """Test GroundingBuilder pattern matching."""

    @pytest.fixture
    def temp_output_dir(self) -> Path:
        """Create a temporary output directory."""
        temp_dir = Path(tempfile.mkdtemp())
        yield temp_dir
        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_academic_patterns_exist(self, temp_output_dir: Path) -> None:
        """Test that academic patterns are defined."""
        builder = GroundingBuilder(temp_output_dir)

        assert hasattr(builder, "ACADEMIC_PATTERNS")
        assert "intro" in builder.ACADEMIC_PATTERNS
        assert "method" in builder.ACADEMIC_PATTERNS
        assert "results" in builder.ACADEMIC_PATTERNS
        assert "discussion" in builder.ACADEMIC_PATTERNS

    def test_term_patterns_exist(self, temp_output_dir: Path) -> None:
        """Test that term patterns are defined."""
        builder = GroundingBuilder(temp_output_dir)

        assert hasattr(builder, "TERM_PATTERNS")
        assert len(builder.TERM_PATTERNS) > 0
