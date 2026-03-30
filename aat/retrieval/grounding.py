"""GroundingBuilder for creating TermBank and PhraseBank from Chinese corpus.

Processes Chinese corpus chunks to extract terminology and academic patterns
for translation grounding.
"""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class TermEntry:
    """A single term entry in the TermBank."""

    source_term: str
    target_term: str | None = None
    evidence: list[str] = field(default_factory=list)
    confidence: float = 0.0
    frequency: int = 0

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "source_term": self.source_term,
            "target_term": self.target_term,
            "evidence": self.evidence,
            "confidence": self.confidence,
            "frequency": self.frequency,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TermEntry":
        """Create from dictionary."""
        return cls(
            source_term=data["source_term"],
            target_term=data.get("target_term"),
            evidence=data.get("evidence", []),
            confidence=data.get("confidence", 0.0),
            frequency=data.get("frequency", 0),
        )


@dataclass
class PhraseEntry:
    """A single phrase entry in the PhraseBank."""

    pattern: str
    category: str  # "intro", "method", "results", "discussion", "general"
    examples: list[str] = field(default_factory=list)
    frequency: int = 0

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "pattern": self.pattern,
            "category": self.category,
            "examples": self.examples,
            "frequency": self.frequency,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PhraseEntry":
        """Create from dictionary."""
        return cls(
            pattern=data["pattern"],
            category=data["category"],
            examples=data.get("examples", []),
            frequency=data.get("frequency", 0),
        )


@dataclass
class TermBank:
    """Collection of terminology entries."""

    entries: dict[str, TermEntry] = field(default_factory=dict)
    source_corpus: str = ""
    generated_at: str = ""

    def add_term(self, term: str, entry: TermEntry) -> None:
        """Add a term entry."""
        self.entries[term] = entry

    def get_term(self, term: str) -> TermEntry | None:
        """Get a term entry."""
        return self.entries.get(term)

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "entries": {k: v.to_dict() for k, v in self.entries.items()},
            "source_corpus": self.source_corpus,
            "generated_at": self.generated_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TermBank":
        """Create from dictionary."""
        bank = cls(
            source_corpus=data.get("source_corpus", ""),
            generated_at=data.get("generated_at", ""),
        )
        for k, v in data.get("entries", {}).items():
            bank.entries[k] = TermEntry.from_dict(v)
        return bank


@dataclass
class PhraseBank:
    """Collection of phrase entries."""

    entries: dict[str, PhraseEntry] = field(default_factory=dict)
    source_corpus: str = ""
    generated_at: str = ""

    def add_phrase(self, phrase: str, entry: PhraseEntry) -> None:
        """Add a phrase entry."""
        self.entries[phrase] = entry

    def get_phrase(self, phrase: str) -> PhraseEntry | None:
        """Get a phrase entry."""
        return self.entries.get(phrase)

    def get_by_category(self, category: str) -> list[PhraseEntry]:
        """Get all entries in a category."""
        return [e for e in self.entries.values() if e.category == category]

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "entries": {k: v.to_dict() for k, v in self.entries.items()},
            "source_corpus": self.source_corpus,
            "generated_at": self.generated_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PhraseBank":
        """Create from dictionary."""
        bank = cls(
            source_corpus=data.get("source_corpus", ""),
            generated_at=data.get("generated_at", ""),
        )
        for k, v in data.get("entries", {}).items():
            bank.entries[k] = PhraseEntry.from_dict(v)
        return bank


class GroundingBuilder:
    """Builds TermBank and PhraseBank from Chinese corpus.

    Processes Chinese corpus chunks to extract:
    - Terminology entries with evidence
    - Academic phrase patterns

    Deterministic in tests using heuristics (no LLM calls).
    """

    # Common Chinese academic terms (deterministic extraction)
    ACADEMIC_PATTERNS = {
        "intro": [
            r"本文.*?研究",
            r"本文.*?探讨",
            r"本文.*?分析",
            r"针对.*?问题",
            r"为了.*?目的",
        ],
        "method": [
            r"采用.*?方法",
            r"使用.*?技术",
            r"通过.*?手段",
            r"基于.*?模型",
            r"实验.*?设计",
        ],
        "results": [
            r"结果.*?表明",
            r"结果.*?显示",
            r"结果.*?证明",
            r"发现.*?现象",
            r"数据.*?显示",
        ],
        "discussion": [
            r"讨论.*?表明",
            r"讨论.*?分析",
            r"综上所述",
            r"总结.*?得出",
            r"因此.*?认为",
        ],
    }

    # Common academic terms for extraction
    TERM_PATTERNS = [
        r"[\u4e00-\u9fa5]{2,6}性",  # X性 (e.g., 有效性, 可靠性)
        r"[\u4e00-\u9fa5]{2,6}度",  # X度 (e.g., 准确度, 精度)
        r"[\u4e00-\u9fa5]{2,6}率",  # X率 (e.g., 准确率, 召回率)
        r"[\u4e00-\u9fa5]{2,6}方法",  # X方法
        r"[\u4e00-\u9fa5]{2,6}模型",  # X模型
        r"[\u4e00-\u9fa5]{2,6}算法",  # X算法
        r"[\u4e00-\u9fa5]{2,6}技术",  # X技术
        r"[\u4e00-\u9fa5]{2,6}系统",  # X系统
        r"[\u4e00-\u9fa5]{2,6}理论",  # X理论
    ]

    def __init__(self, output_dir: Path) -> None:
        """
        Initialize the grounding builder.

        Args:
            output_dir: Directory to save termbank.json and phrasebank.json.
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.termbank = TermBank(
            source_corpus="",
            generated_at="",
        )
        self.phrasebank = PhraseBank(
            source_corpus="",
            generated_at="",
        )

    def process_corpus(self, chunks: list[dict]) -> dict:
        """
        Process corpus chunks to build TermBank and PhraseBank.

        Args:
            chunks: List of corpus chunks with "text" and "metadata".

        Returns:
            Dictionary with term and phrase counts.
        """
        from datetime import datetime

        timestamp = datetime.now().isoformat()
        self.termbank.generated_at = timestamp
        self.phrasebank.generated_at = timestamp

        term_count = 0
        phrase_count = 0

        for chunk in chunks:
            text = chunk.get("text", "")
            if not text:
                continue

            # Only process Chinese text
            metadata = chunk.get("metadata", {})
            if metadata.get("language") != "zh":
                continue

            # Extract terms
            terms = self._extract_terms(text)
            for term in terms:
                if term not in self.termbank.entries:
                    self.termbank.entries[term] = TermEntry(
                        source_term=term,
                        evidence=[],
                        frequency=0,
                    )
                entry = self.termbank.entries[term]
                entry.frequency += 1
                if len(entry.evidence) < 5:  # Keep up to 5 examples
                    entry.evidence.append(text[:200])  # Truncate for storage
                term_count += 1

            # Extract phrases
            phrases = self._extract_phrases(text)
            for pattern, category in phrases:
                key = f"{category}:{pattern}"
                if key not in self.phrasebank.entries:
                    self.phrasebank.entries[key] = PhraseEntry(
                        pattern=pattern,
                        category=category,
                        examples=[],
                        frequency=0,
                    )
                entry = self.phrasebank.entries[key]
                entry.frequency += 1
                if len(entry.examples) < 5:  # Keep up to 5 examples
                    entry.examples.append(text[:200])
                phrase_count += 1

        return {
            "terms": term_count,
            "phrases": phrase_count,
            "unique_terms": len(self.termbank.entries),
            "unique_phrases": len(self.phrasebank.entries),
        }

    def _extract_terms(self, text: str) -> list[str]:
        """Extract potential terms from Chinese text.

        Args:
            text: Chinese text to process.

        Returns:
            List of extracted terms.
        """
        terms = []
        for pattern in self.TERM_PATTERNS:
            matches = re.findall(pattern, text)
            terms.extend(matches)
        return list(set(terms))  # Deduplicate

    def _extract_phrases(self, text: str) -> list[tuple[str, str]]:
        """Extract academic phrases from Chinese text.

        Args:
            text: Chinese text to process.

        Returns:
            List of (pattern, category) tuples.
        """
        phrases = []
        for category, patterns in self.ACADEMIC_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, text):
                    phrases.append((pattern, category))
        return phrases

    def save(self) -> dict[str, Path]:
        """Save termbank and phrasebank to JSON files.

        Returns:
            Dictionary with paths to saved files.
        """
        termbank_path = self.output_dir / "termbank.json"
        phrasebank_path = self.output_dir / "phrasebank.json"

        with open(termbank_path, "w", encoding="utf-8") as f:
            json.dump(self.termbank.to_dict(), f, ensure_ascii=False, indent=2)

        with open(phrasebank_path, "w", encoding="utf-8") as f:
            json.dump(self.phrasebank.to_dict(), f, ensure_ascii=False, indent=2)

        return {
            "termbank": termbank_path,
            "phrasebank": phrasebank_path,
        }

    def load(self) -> bool:
        """Load termbank and phrasebank from JSON files.

        Returns:
            True if both files loaded successfully, False otherwise.
        """
        termbank_path = self.output_dir / "termbank.json"
        phrasebank_path = self.output_dir / "phrasebank.json"

        if not termbank_path.exists() or not phrasebank_path.exists():
            return False

        try:
            with open(termbank_path, "r", encoding="utf-8") as f:
                termbank_data = json.load(f)
                self.termbank = TermBank.from_dict(termbank_data)

            with open(phrasebank_path, "r", encoding="utf-8") as f:
                phrasebank_data = json.load(f)
                self.phrasebank = PhraseBank.from_dict(phrasebank_data)

            return True
        except (json.JSONDecodeError, KeyError):
            return False
