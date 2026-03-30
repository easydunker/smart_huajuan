"""Hierarchical Context Assembler for segment translation."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

# Runtime imports for type hints
if TYPE_CHECKING:
    from aat.storage.models import TranslationMemory

# These imports are needed at runtime for tests to work
from aat.orchestrator.style_guide import StyleGuide
from aat.orchestrator.chapter_summary import ChapterSummary


@dataclass
class ContextConfig:
    """Configuration for context assembly."""

    max_tokens: int = 4000
    include_global_style: bool = True
    include_termbank: bool = True
    include_previous_segment: bool = True
    include_chapter_summary: bool = True


@dataclass
class AssembledContext:
    """Assembled hierarchical context for a segment."""

    segment_id: str
    context_text: str
    chapter_id: str | None = None
    components: dict = field(default_factory=dict)
    token_count: int = 0
    truncated: bool = False


class ContextAssembler:
    """Assemble hierarchical context for segment translation."""

    def __init__(
        self,
        project_dir: Path,
        config: ContextConfig | None = None,
    ) -> None:
        """
        Initialize context assembler.

        Args:
            project_dir: Project directory path.
            config: Optional context configuration.
        """
        self.project_dir = Path(project_dir)
        self.config = config or ContextConfig()

    def assemble_context_for_segment(
        self,
        segment_id: str,
        chapter_id: str | None = None,
        termbank: dict | None = None,
        previous_translation: str | None = None,
        chapter_summary: ChapterSummary | None = None,
        global_style: StyleGuide | None = None,
    ) -> AssembledContext:
        """
        Assemble hierarchical context for a segment.

        Args:
            segment_id: Segment identifier.
            chapter_id: Optional chapter identifier.
            termbank: Translation memory with locked entries.
            previous_translation: Previous segment's translation.
            chapter_summary: Summary of previous chapter.
            global_style: Global style guide.

        Returns:
            AssembledContext with assembled text and metadata.
        """
        components = {}
        context_parts = []

        # 1. Global Style Guide
        if self.config.include_global_style and global_style:
            style_text = self._format_style_guide(global_style)
            components["global_style"] = style_text
            context_parts.append(style_text)
            context_parts.append("\n\n")

        # 2. Termbank (locked entries)
        if self.config.include_termbank and termbank:
            termbank_text = self._format_termbank(termbank)
            components["termbank"] = termbank_text
            context_parts.append(termbank_text)
            context_parts.append("\n\n")

        # 3. Chapter Summary (from previous chapter)
        if self.config.include_chapter_summary and chapter_summary:
            summary_text = self._format_chapter_summary(chapter_summary)
            components["chapter_summary"] = summary_text
            context_parts.append(summary_text)
            context_parts.append("\n\n")

        # 4. Previous Segment Translation
        if self.config.include_previous_segment and previous_translation:
            previous_text = self._format_previous_segment(previous_translation)
            components["previous_segment"] = previous_text
            context_parts.append(previous_text)
            context_parts.append("\n\n")

        # Combine all parts
        full_context = "".join(context_parts)

        # Enforce token budget
        token_count = self._estimate_tokens(full_context)
        truncated = False

        if token_count > self.config.max_tokens:
            # Safe truncation: remove from end
            # Assuming ~4 chars per token
            max_chars = self.config.max_tokens * 4
            full_context = full_context[:max_chars]
            full_context += "\n\n[Context truncated due to token limit]"
            token_count = self._estimate_tokens(full_context)
            truncated = True

        return AssembledContext(
            segment_id=segment_id,
            chapter_id=chapter_id,
            context_text=full_context,
            components=components,
            token_count=token_count,
            truncated=truncated,
        )

    def _format_style_guide(self, style_guide: StyleGuide) -> str:
        """Format global style guide for context."""
        constraints = style_guide.constraints
        parts = ["【全局翻译风格指导】"]

        for category, items in constraints.items():
            parts.append(f"\n{category}:")
            for item in items[:3]:  # Limit to 3 items per category
                parts.append(f"  - {item}")

        return "\n".join(parts)

    def _format_termbank(self, termbank: dict) -> str:
        """Format translation memory (termbank) for context."""
        parts = ["【术语库（已锁定）】"]

        # Get locked entries only
        locked_entries = termbank.get("locked", [])

        for entry in locked_entries[:10]:  # Limit to 10 entries
            source = entry.get("source_phrase", "")
            target = entry.get("target_phrase", "")
            if source and target:
                parts.append(f"  {source} → {target}")

        return "\n".join(parts)

    def _format_chapter_summary(
        self, chapter_summary: ChapterSummary
    ) -> str:
        """Format chapter summary for context."""
        return (
            f"【前一章摘要】\n"
            f"章节: {chapter_summary.chapter_id}\n"
            f"摘要: {chapter_summary.summary}"
        )

    def _format_previous_segment(
        self, previous_translation: str
    ) -> str:
        """Format previous segment translation for context."""
        # Show first 300 characters as context
        preview = previous_translation[:300]
        if len(previous_translation) > 300:
            preview += "..."
        return f"【前一段翻译】\n{preview}"

    def _estimate_tokens(self, text: str) -> int:
        """
        Estimate token count for text.

        For Chinese text, approximate 1 token per 4 characters.
        For English/mixed, approximate 1 token per 4 characters.

        Args:
            text: Text to estimate.

        Returns:
            Estimated token count.
        """
        if not text:
            return 0

        # Simple approximation: ~4 chars per token for mixed content
        return len(text) // 4

    def get_context_stats(self) -> dict:
        """
        Get statistics about context assembly.

        Returns:
            Dictionary with context assembly stats.
        """
        return {
            "max_tokens": self.config.max_tokens,
            "include_global_style": self.config.include_global_style,
            "include_termbank": self.config.include_termbank,
            "include_previous_segment": self.config.include_previous_segment,
            "include_chapter_summary": self.config.include_chapter_summary,
        }
