"""Chapter-based export functionality."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING
from collections import defaultdict
import hashlib
import json

if TYPE_CHECKING:
    from aat.storage.models import (
        DocumentModel,
        Section,
        Paragraph,
        TranslationSegment,
    )


class ChapterExportError(Exception):
    """Exception raised for chapter export errors."""


@dataclass
class SegmentCheckpoint:
    """Segment-level checkpoint data."""

    sid: str
    source_hash: str
    translation: str | None
    state: str
    validator_results: list[dict] = field(default_factory=list)
    critic_issues: list[dict] = field(default_factory=list)
    uncertainties: list[dict] = field(default_factory=list)
    user_comments: str | None = None
    timestamp: str | None = None
    locked: bool = False
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "sid": self.sid,
            "source_hash": self.source_hash,
            "translation": self.translation,
            "state": self.state,
            "validator_results": self.validator_results,
            "critic_issues": self.critic_issues,
            "uncertainties": self.uncertainties,
            "user_comments": self.user_comments,
            "timestamp": self.timestamp,
            "locked": self.locked,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SegmentCheckpoint":
        """Create from dictionary."""
        return cls(
            sid=data["sid"],
            source_hash=data["source_hash"],
            translation=data.get("translation"),
            state=data["state"],
            validator_results=data.get("validator_results", []),
            critic_issues=data.get("critic_issues", []),
            uncertainties=data.get("uncertainties", []),
            user_comments=data.get("user_comments"),
            timestamp=data.get("timestamp"),
            locked=data.get("locked", False),
            metadata=data.get("metadata", {}),
        )

    @classmethod
    def create_from_segment(
        cls,
        sid: str,
        source_text: str,
        translation: str | None,
        state: str,
        validator_results: list[dict] | None = None,
        critic_issues: list[dict] | None = None,
        uncertainties: list[dict] | None = None,
        user_comments: str | None = None,
        locked: bool = False,
    ) -> "SegmentCheckpoint":
        """Create checkpoint from translation segment."""
        source_hash = hashlib.sha256(source_text.encode("utf-8")).hexdigest()
        return cls(
            sid=sid,
            source_hash=source_hash,
            translation=translation,
            state=state,
            validator_results=validator_results or [],
            critic_issues=critic_issues or [],
            uncertainties=uncertainties or [],
            user_comments=user_comments,
            locked=locked,
        )

    def is_approved(self) -> bool:
        """Check if segment is approved (locked)."""
        return self.locked and self.translation is not None


class ChapterExporter:
    """Export approved segments by chapter."""

    def __init__(self, project_dir: Path) -> None:
        """
        Initialize chapter exporter.

        Args:
            project_dir: Project directory containing checkpoints and data.
        """
        self.project_dir = project_dir
        self.checkpoints_dir = project_dir / "checkpoints"
        self.metadata_file = project_dir / "metadata.json"

    def load_segment_checkpoints(self) -> dict[str, SegmentCheckpoint]:
        """
        Load all segment checkpoints.

        Returns:
            Dictionary mapping segment IDs to SegmentCheckpoint objects.
        """
        checkpoints = {}
        if not self.checkpoints_dir.exists():
            return checkpoints

        checkpoint_files = list(self.checkpoints_dir.glob("checkpoint_*.json"))
        for checkpoint_file in checkpoint_files:
            try:
                with open(checkpoint_file, "r", encoding="utf-8") as f:
                    data = json.load(f)

                # Extract segment states from checkpoint
                segment_states = data.get("segment_states", {})
                for sid, state_data in segment_states.items():
                    if isinstance(state_data, dict):
                        checkpoint = SegmentCheckpoint(
                            sid=sid,
                            source_hash=state_data.get("source_hash", ""),
                            translation=state_data.get("translation"),
                            state=state_data.get("state", ""),
                            validator_results=state_data.get("validator_results", []),
                            critic_issues=state_data.get("critic_issues", []),
                            uncertainties=state_data.get("uncertainties", []),
                            user_comments=state_data.get("user_comments"),
                            timestamp=state_data.get("timestamp"),
                            locked=state_data.get("locked", False),
                            metadata=state_data.get("metadata", {}),
                        )
                        checkpoints[sid] = checkpoint
            except (json.JSONDecodeError, KeyError):
                # Skip corrupted checkpoint files
                continue

        return checkpoints

    def get_chapter_segments(
        self,
        chapter_id: str,
        segment_checkpoints: dict[str, SegmentCheckpoint],
    ) -> list[SegmentCheckpoint]:
        """
        Get approved segments for a specific chapter.

        Args:
            chapter_id: Chapter identifier.
            segment_checkpoints: Dictionary of all segment checkpoints.

        Returns:
            List of approved SegmentCheckpoint objects for chapter.
        """
        # Load project metadata to map segments to chapters
        try:
            with open(self.metadata_file, "r", encoding="utf-8") as f:
                metadata = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            # Try to infer chapter mapping from checkpoint metadata
            metadata = {}

        chapter_segments = []
        for sid, checkpoint in segment_checkpoints.items():
            # Check if segment belongs to chapter
            # This is a simplified approach - in production, you'd have
            # a proper segment-to-chapter mapping in metadata
            segment_metadata = checkpoint.metadata or {}
            if segment_metadata.get("chapter_id") == chapter_id or self._is_segment_in_chapter(
                sid, chapter_id, metadata
            ):
                if checkpoint.is_approved():
                    chapter_segments.append(checkpoint)

        return chapter_segments

    def _is_segment_in_chapter(
        self, sid: str, chapter_id: str, metadata: dict
    ) -> bool:
        """
        Check if a segment belongs to a chapter.

        Args:
            sid: Segment ID.
            chapter_id: Chapter identifier.
            metadata: Project metadata.

        Returns:
            True if segment belongs to chapter.
        """
        segment_map = metadata.get("segment_chapter_map", {})
        return segment_map.get(sid) == chapter_id

    def export_chapter(
        self,
        chapter_id: str,
        output_path: Path | None = None,
    ) -> dict:
        """
        Export approved segments for a chapter.

        Args:
            chapter_id: Chapter identifier.
            output_path: Optional output file path.

        Returns:
            Dictionary containing:
                - 'success': Boolean indicating success
                - 'exported_segments': List of exported segments
                - 'warnings': List of warnings
                - 'output_path': Path to exported file (if output_path provided)
        """
        # Load all segment checkpoints
        segment_checkpoints = self.load_segment_checkpoints()

        # Get approved segments for chapter
        chapter_segments = self.get_chapter_segments(chapter_id, segment_checkpoints)

        warnings = []

        # Check if some segments might be unapproved
        total_in_chapter = sum(
            1
            for sid, cp in segment_checkpoints.items()
            if cp.metadata.get("chapter_id") == chapter_id
        )
        if total_in_chapter > len(chapter_segments):
            warnings.append(
                f"Not all segments in chapter {chapter_id} are approved. "
                f"{len(chapter_segments)}/{total_in_chapter} segments exported."
            )

        result = {
            "success": True,
            "exported_segments": [seg.to_dict() for seg in chapter_segments],
            "warnings": warnings,
            "output_path": None,
        }

        # Write to file if output path provided
        if output_path:
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)

            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)

            result["output_path"] = str(output_path)

        return result

    def list_chapters(self) -> list[dict]:
        """
        List all chapters with their approval status.

        Returns:
            List of chapter dictionaries with chapter_id and status info.
        """
        # Load segment checkpoints
        segment_checkpoints = self.load_segment_checkpoints()

        # Group segments by chapter
        chapter_map: dict[str, dict] = defaultdict(
            lambda: {"total": 0, "approved": 0, "segments": []}
        )

        for sid, checkpoint in segment_checkpoints.items():
            chapter_id = checkpoint.metadata.get("chapter_id", "unknown")
            chapter_map[chapter_id]["total"] += 1
            if checkpoint.is_approved():
                chapter_map[chapter_id]["approved"] += 1
            chapter_map[chapter_id]["segments"].append(sid)

        # Convert to list of dictionaries
        chapters = []
        for chapter_id, info in chapter_map.items():
            chapters.append(
                {
                    "chapter_id": chapter_id,
                    "total_segments": info["total"],
                    "approved_segments": info["approved"],
                    "complete": info["total"] > 0 and info["total"] == info["approved"],
                }
            )

        # Sort by chapter_id
        chapters.sort(key=lambda x: x["chapter_id"])

        return chapters
