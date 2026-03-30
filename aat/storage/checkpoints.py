"""Checkpoint system for saving and loading translation state."""

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

if TYPE_CHECKING:
    from aat.storage.models import TranslationProject, TranslationSegment


class CheckpointError(Exception):
    """Exception raised for checkpoint operations."""


@dataclass
class Checkpoint:
    """Checkpoint data structure."""

    project_id: str
    timestamp: str
    segment_states: dict
    metadata: dict
    preferences: dict = field(default_factory=dict)

    @classmethod
    def create(cls, project: "TranslationProject") -> "Checkpoint":
        """Create a checkpoint from a project."""
        return cls(
            project_id=project.project_id,
            timestamp=datetime.now().isoformat(),
            segment_states={
                seg.segment.sid: asdict(seg) for seg in project.segments
            },
            metadata={
                "title": project.document.title,
                "total_segments": len(project.segments),
                "completed_segments": sum(
                    1 for seg in project.segments if seg.locked
                ),
            },
        )

    def to_json(self) -> str:
        """Convert checkpoint to JSON string."""
        data = {
            "project_id": self.project_id,
            "timestamp": self.timestamp,
            "segment_states": self.segment_states,
            "metadata": self.metadata,
            "preferences": self.preferences,
        }
        return json.dumps(data, ensure_ascii=False, indent=2)

    @classmethod
    def from_json(cls, json_str: str) -> "Checkpoint":
        """Create checkpoint from JSON string."""
        data = json.loads(json_str)
        return cls(
            project_id=data["project_id"],
            timestamp=data["timestamp"],
            segment_states=data["segment_states"],
            metadata=data["metadata"],
            preferences=data.get("preferences", {}),
        )


class CheckpointManager:
    """Manage checkpoint files."""

    def __init__(self, project_dir: Path) -> None:
        """
        Initialize checkpoint manager.

        Args:
            project_dir: Directory to store checkpoints.
        """
        self.project_dir = project_dir
        self.checkpoints_dir = project_dir / "checkpoints"
        self.checkpoints_dir.mkdir(parents=True, exist_ok=True)

    def save_checkpoint(self, checkpoint: Checkpoint) -> Path:
        """
        Save checkpoint to file.

        Args:
            checkpoint: Checkpoint data to save.

        Returns:
            Path to saved checkpoint file.
        """
        timestamp = checkpoint.timestamp.replace(":", "-").replace(".", "-")
        filename = f"checkpoint_{timestamp}.json"
        filepath = self.checkpoints_dir / filename

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(checkpoint.to_json())

        return filepath

    def load_latest_checkpoint(self) -> Checkpoint | None:
        """
        Load the most recent checkpoint.

        Returns:
            Most recent Checkpoint or None if no checkpoints exist.
        """
        checkpoints = self.list_checkpoints()
        if not checkpoints:
            return None

        # Sort by timestamp (newest first)
        checkpoints.sort(key=lambda p: p.name, reverse=True)
        latest_path = checkpoints[0]

        with open(latest_path, "r", encoding="utf-8") as f:
            return Checkpoint.from_json(f.read())

    def list_checkpoints(self) -> list[Path]:
        """
        List all checkpoint files.

        Returns:
            List of checkpoint file paths, sorted by modification time.
        """
        if not self.checkpoints_dir.exists():
            return []

        checkpoints = list(self.checkpoints_dir.glob("checkpoint_*.json"))
        # Sort by modification time (newest first)
        checkpoints.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        return checkpoints

    def cleanup_old_checkpoints(self, keep_count: int = 10) -> None:
        """
        Remove old checkpoints, keeping only the most recent ones.

        Args:
            keep_count: Number of recent checkpoints to keep.
        """
        checkpoints = self.list_checkpoints()

        # Remove all but the most recent ones
        for checkpoint_path in checkpoints[keep_count:]:
            checkpoint_path.unlink()

    def update_segment(self, sid: str, updates: dict) -> bool:
        """Merge updates into a segment's state dict and save.

        Returns False if no checkpoint exists or sid not found.
        """
        checkpoint = self.load_latest_checkpoint()
        if not checkpoint:
            return False
        if sid not in checkpoint.segment_states:
            return False
        checkpoint.segment_states[sid].update(updates)
        self.save_checkpoint(checkpoint)
        return True

    def lock_segment(self, sid: str) -> bool:
        """Mark a segment as locked (approved)."""
        return self.update_segment(sid, {"locked": True, "state": "lock_segment"})

    def add_comment(self, sid: str, comment: str) -> bool:
        """Append a timestamped user comment to a segment."""
        checkpoint = self.load_latest_checkpoint()
        if not checkpoint:
            return False
        if sid not in checkpoint.segment_states:
            return False
        seg = checkpoint.segment_states[sid]
        comments = seg.get("user_comments", [])
        if not isinstance(comments, list):
            comments = []
        elif comments and isinstance(comments[0], str):
            comments = [{"text": s, "timestamp": "unknown"} for s in comments]
        comments.append({"text": comment, "timestamp": datetime.now().isoformat()})
        seg["user_comments"] = comments
        self.save_checkpoint(checkpoint)
        return True

    def update_translation(self, sid: str, new_translation: str) -> bool:
        """Replace a segment's translation text."""
        return self.update_segment(sid, {"translation": new_translation})

    def request_revision(self, sid: str) -> bool:
        """Mark a segment for revision: set revision_requested, unlock, change state."""
        return self.update_segment(sid, {
            "revision_requested": True,
            "state": "user_feedback_wait",
            "locked": False,
        })

    def add_structured_feedback(
        self, sid: str, category: str, detail: str,
        span: str | None = None, suggested_fix: str | None = None,
    ) -> bool:
        """Append a structured feedback item to a segment."""
        checkpoint = self.load_latest_checkpoint()
        if not checkpoint:
            return False
        if sid not in checkpoint.segment_states:
            return False
        seg = checkpoint.segment_states[sid]
        fb_list = seg.get("structured_feedback", [])
        if not isinstance(fb_list, list):
            fb_list = []
        fb_item: dict = {
            "category": category,
            "detail": detail,
            "timestamp": datetime.now().isoformat(),
        }
        if span:
            fb_item["span"] = span
        if suggested_fix:
            fb_item["suggested_fix"] = suggested_fix
        fb_list.append(fb_item)
        seg["structured_feedback"] = fb_list
        self.save_checkpoint(checkpoint)
        return True

    def set_project_preferences(self, preferences: dict) -> bool:
        """Save project-level preferences into the latest checkpoint."""
        checkpoint = self.load_latest_checkpoint()
        if not checkpoint:
            return False
        checkpoint.preferences = preferences
        self.save_checkpoint(checkpoint)
        return True

    def get_project_preferences(self) -> dict:
        """Load project-level preferences from the latest checkpoint."""
        checkpoint = self.load_latest_checkpoint()
        if checkpoint:
            return checkpoint.preferences
        return {}

    def get_project_metadata(self) -> dict | None:
        """
        Get project metadata from latest checkpoint.

        Returns:
            Metadata dict or None if no checkpoint exists.
        """
        checkpoint = self.load_latest_checkpoint()
        if checkpoint:
            return checkpoint.metadata
        return None


def create_checkpoint_manager(project_id: str | None = None) -> CheckpointManager:
    """
    Factory function to create checkpoint manager.

    Args:
        project_id: Project ID. If None, uses a temp directory.

    Returns:
        CheckpointManager instance.
    """
    if project_id:
        project_dir = Path.cwd() / "projects" / project_id
    else:
        import tempfile
        project_dir = Path(tempfile.mkdtemp())

    return CheckpointManager(project_dir)
