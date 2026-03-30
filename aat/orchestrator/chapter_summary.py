"""Chapter Summary Generator for hierarchical context."""

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from aat.storage.models import TranslationProject, DocumentModel


@dataclass
class ChapterSummary:
    """Summary of a chapter for context propagation."""

    project_id: str
    chapter_id: str
    summary: str
    generated_at: str
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "project_id": self.project_id,
            "chapter_id": self.chapter_id,
            "summary": self.summary,
            "generated_at": self.generated_at,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ChapterSummary":
        """Create from dictionary."""
        return cls(
            project_id=data["project_id"],
            chapter_id=data["chapter_id"],
            summary=data["summary"],
            generated_at=data["generated_at"],
            metadata=data.get("metadata", {}),
        )

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    @classmethod
    def from_json(cls, json_str: str) -> "ChapterSummary":
        """Create from JSON string."""
        return cls.from_dict(json.loads(json_str))


def generate_chapter_summary(
    project_id: str,
    chapter_id: str,
    chapter_segments: list[dict],
    max_tokens: int = 200,
) -> ChapterSummary:
    """
    Generate a summary for a completed chapter.

    Args:
        project_id: Project identifier.
        chapter_id: Chapter identifier.
        chapter_segments: List of segment dictionaries with translations.
        max_tokens: Maximum token length for summary (default: 200).

    Returns:
        ChapterSummary object with generated summary.
    """
    # Combine translations from approved segments
    translations = []
    for segment in chapter_segments:
        if segment.get("locked") and segment.get("translation"):
            translations.append(segment["translation"])

    # Generate summary from translations
    if translations:
        combined_text = " ".join(translations)

        # Simple truncation for summary (in production, use LLM)
        # For now, use first N characters as a proxy for tokens
        # Assuming ~4 chars per token for Chinese text
        max_chars = max_tokens * 4
        summary = combined_text[:max_chars]

        if len(combined_text) > max_chars:
            summary += "..."
    else:
        summary = "Chapter completed with no approved segments."

    return ChapterSummary(
        project_id=project_id,
        chapter_id=chapter_id,
        summary=summary,
        generated_at=datetime.now().isoformat(),
        metadata={
            "segment_count": len(chapter_segments),
            "approved_count": len(translations),
            "max_tokens": max_tokens,
        },
    )


def save_chapter_summary(
    chapter_summary: ChapterSummary,
    project_dir: Path,
) -> Path:
    """
    Save chapter summary to project directory.

    Args:
        chapter_summary: ChapterSummary object to save.
        project_dir: Project directory path.

    Returns:
        Path to saved chapter summary file.
    """
    project_dir = Path(project_dir)
    summaries_dir = project_dir / "summaries"
    summaries_dir.mkdir(parents=True, exist_ok=True)

    output_path = summaries_dir / f"chapter_{chapter_summary.chapter_id}.json"

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(chapter_summary.to_json())

    return output_path


def load_chapter_summary(
    chapter_id: str,
    project_dir: Path,
) -> ChapterSummary | None:
    """
    Load chapter summary from project directory.

    Args:
        chapter_id: Chapter identifier.
        project_dir: Project directory path.

    Returns:
        ChapterSummary object or None if not found.
    """
    project_dir = Path(project_dir)
    summaries_dir = project_dir / "summaries"

    if not summaries_dir.exists():
        return None

    input_path = summaries_dir / f"chapter_{chapter_id}.json"

    if not input_path.exists():
        return None

    with open(input_path, "r", encoding="utf-8") as f:
        return ChapterSummary.from_json(f.read())


def list_chapter_summaries(project_dir: Path) -> list[ChapterSummary]:
    """
    List all chapter summaries in project directory.

    Args:
        project_dir: Project directory path.

    Returns:
        List of ChapterSummary objects.
    """
    project_dir = Path(project_dir)
    summaries_dir = project_dir / "summaries"

    if not summaries_dir.exists():
        return []

    summaries = []
    for summary_file in summaries_dir.glob("chapter_*.json"):
        try:
            with open(summary_file, "r", encoding="utf-8") as f:
                summaries.append(ChapterSummary.from_json(f.read()))
        except (json.JSONDecodeError, KeyError):
            # Skip corrupted files
            continue

    return summaries
