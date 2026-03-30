"""Global Style Guide Generator for academic translation."""

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from aat.storage.models import TranslationProject


@dataclass
class StyleGuide:
    """Global style guide for Chinese academic translation."""

    project_id: str
    generated_at: str
    constraints: dict[str, list[str]] = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "project_id": self.project_id,
            "generated_at": self.generated_at,
            "constraints": self.constraints,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "StyleGuide":
        """Create from dictionary."""
        return cls(
            project_id=data["project_id"],
            generated_at=data["generated_at"],
            constraints=data.get("constraints", {}),
            metadata=data.get("metadata", {}),
        )

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    @classmethod
    def from_json(cls, json_str: str) -> "StyleGuide":
        """Create from JSON string."""
        return cls.from_dict(json.loads(json_str))


def generate_style_guide(
    project_id: str,
    target_language: str = "zh",
    style_level: str = "academic",
) -> StyleGuide:
    """
    Generate a global style guide for Chinese academic translation.

    Args:
        project_id: Project identifier.
        target_language: Target language (default: zh for Chinese).
        style_level: Style level (academic, formal, etc.).

    Returns:
        StyleGuide object with constraints.
    """
    if target_language == "zh":
        # Chinese academic style constraints
        constraints = {
            "sentence_structure": [
                "Use clear, concise sentence structures",
                "Maintain logical flow between sentences",
                "Avoid overly long or complex sentences",
            ],
            "vocabulary": [
                "Use formal academic terminology",
                "Maintain consistency in terminology use",
                "Use standard Chinese academic phrases",
            ],
            "citation_format": [
                "Preserve citation format exactly as in source",
                "Do not modify author names or years",
                "Maintain citation brackets/parentheses style",
            ],
            "number_format": [
                "Preserve all numerical values exactly",
                "Maintain decimal points and ranges",
                "Do not convert units or measurements",
            ],
            "punctuation": [
                "Use Chinese punctuation where appropriate",
                "Maintain proper quotation mark styles",
                "Use correct full-width characters",
            ],
            "academic_conventions": [
                "Use passive voice where appropriate in academic contexts",
                "Maintain objective, scholarly tone",
                "Avoid colloquial expressions",
                "Use proper transition phrases between ideas",
            ],
        }
    else:
        # Generic constraints for other languages
        constraints = {
            "general": [
                "Maintain academic tone",
                "Preserve citation and number format",
                "Ensure consistency in terminology",
            ],
        }

    return StyleGuide(
        project_id=project_id,
        generated_at=datetime.now().isoformat(),
        constraints=constraints,
        metadata={
            "target_language": target_language,
            "style_level": style_level,
        },
    )


def save_style_guide(style_guide: StyleGuide, project_dir: Path) -> Path:
    """
    Save style guide to project directory.

    Args:
        style_guide: StyleGuide object to save.
        project_dir: Project directory path.

    Returns:
        Path to saved style guide file.
    """
    project_dir = Path(project_dir)
    output_path = project_dir / "global_style.json"

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(style_guide.to_json())

    return output_path


def load_style_guide(project_dir: Path) -> StyleGuide | None:
    """
    Load style guide from project directory.

    Args:
        project_dir: Project directory path.

    Returns:
        StyleGuide object or None if not found.
    """
    project_dir = Path(project_dir)
    input_path = project_dir / "global_style.json"

    if not input_path.exists():
        return None

    with open(input_path, "r", encoding="utf-8") as f:
        return StyleGuide.from_json(f.read())
