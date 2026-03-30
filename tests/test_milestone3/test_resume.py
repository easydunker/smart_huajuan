"""Integration tests for resume command."""

import json
import tempfile
from pathlib import Path

import pytest
from click.testing import CliRunner

from aat.cli import main
from aat.storage.checkpoints import CheckpointManager, Checkpoint


class TestResumeCommand:
    """Test resume command integration."""

    @pytest.fixture
    def temp_project_dir(self) -> Path:
        """Create a temporary project directory."""
        return Path(tempfile.mkdtemp())

    @pytest.fixture
    def runner(self) -> CliRunner:
        """Create Click CLI test runner."""
        return CliRunner()

    def test_resume_command_no_checkpoint(self, runner: CliRunner, temp_project_dir: Path) -> None:
        """Test resume command when no checkpoint exists."""
        # Create empty project directory
        temp_project_dir.mkdir(parents=True, exist_ok=True)

        result = runner.invoke(main, ["resume", str(temp_project_dir)])

        assert result.exit_code != 0  # Should fail
        assert "No checkpoint found" in result.output

    def test_resume_command_with_checkpoint(self, runner: CliRunner, temp_project_dir: Path) -> None:
        """Test resume command with valid checkpoint."""
        # Create checkpoint manager
        checkpoint_manager = CheckpointManager(temp_project_dir)

        # Create and save a checkpoint
        checkpoint = Checkpoint(
            project_id="test-project",
            timestamp="2024-01-01T00:00:00",
            segment_states={
                "s1": {
                    "sid": "s1",
                    "state": "LOCKED",
                    "locked": True,
                    "translation": "Translation 1",
                },
                "s2": {
                    "sid": "s2",
                    "state": "DRAFT",
                    "locked": False,
                    "translation": None,
                },
            },
            metadata={
                "title": "Test Document",
                "total_segments": 2,
                "completed_segments": 1,
            },
        )
        checkpoint_manager.save_checkpoint(checkpoint)

        result = runner.invoke(main, ["resume", str(temp_project_dir)])

        assert result.exit_code == 0
        assert "Resuming project:" in result.output
        assert "Project ID: test-project" in result.output
        assert "Progress: 1/2 segments completed" in result.output
        assert "Ready to resume from segment: s2" in result.output

    def test_resume_command_all_locked(self, runner: CliRunner, temp_project_dir: Path) -> None:
        """Test resume command when all segments are locked."""
        checkpoint_manager = CheckpointManager(temp_project_dir)

        # Create checkpoint with all segments locked
        checkpoint = Checkpoint(
            project_id="test-project",
            timestamp="2024-01-01T00:00:00",
            segment_states={
                "s1": {
                    "sid": "s1",
                    "state": "LOCKED",
                    "locked": True,
                    "translation": "Translation 1",
                },
                "s2": {
                    "sid": "s2",
                    "state": "LOCKED",
                    "locked": True,
                    "translation": "Translation 2",
                },
            },
            metadata={
                "title": "Test Document",
                "total_segments": 2,
                "completed_segments": 2,
            },
        )
        checkpoint_manager.save_checkpoint(checkpoint)

        result = runner.invoke(main, ["resume", str(temp_project_dir)])

        assert result.exit_code == 0
        assert "All segments are locked" in result.output
        assert "Translation appears complete" in result.output


class TestResumeIntegration:
    """Integration tests for resume functionality."""

    @pytest.fixture
    def temp_project_dir(self) -> Path:
        """Create a temporary project directory."""
        return Path(tempfile.mkdtemp())

    def test_checkpoint_manager_creates_directory(self, temp_project_dir: Path) -> None:
        """Test that CheckpointManager creates directories."""
        checkpoint_manager = CheckpointManager(temp_project_dir)

        assert temp_project_dir.exists()
        assert (temp_project_dir / "checkpoints").exists()

    def test_save_and_load_checkpoint(self, temp_project_dir: Path) -> None:
        """Test saving and loading a checkpoint."""
        checkpoint_manager = CheckpointManager(temp_project_dir)

        checkpoint = Checkpoint(
            project_id="test-project",
            timestamp="2024-01-01T00:00:00",
            segment_states={
                "s1": {"sid": "s1", "state": "DRAFT", "locked": False},
            },
            metadata={"total_segments": 1, "completed_segments": 0},
        )

        # Save
        saved_path = checkpoint_manager.save_checkpoint(checkpoint)
        assert saved_path.exists()

        # Load
        loaded = checkpoint_manager.load_latest_checkpoint()
        assert loaded is not None
        assert loaded.project_id == checkpoint.project_id
        assert loaded.timestamp == checkpoint.timestamp

    def test_multiple_checkpoints_ordered(self, temp_project_dir: Path) -> None:
        """Test that multiple checkpoints are kept in order."""
        checkpoint_manager = CheckpointManager(temp_project_dir)

        # Save three checkpoints
        for i in range(3):
            checkpoint = Checkpoint(
                project_id="test-project",
                timestamp=f"2024-01-01T00:00:0{i}",
                segment_states={f"s{i}": {"sid": f"s{i}", "locked": False}},
                metadata={"total_segments": 1, "completed_segments": 0},
            )
            checkpoint_manager.save_checkpoint(checkpoint)

        # Load latest
        latest = checkpoint_manager.load_latest_checkpoint()
        assert latest is not None
        assert "2024-01-01T00:00:02" in latest.timestamp

        # List checkpoints
        checkpoints = checkpoint_manager.list_checkpoints()
        assert len(checkpoints) == 3

    def test_cleanup_old_checkpoints(self, temp_project_dir: Path) -> None:
        """Test cleanup of old checkpoints."""
        checkpoint_manager = CheckpointManager(temp_project_dir)

        # Save many checkpoints
        for i in range(15):
            checkpoint = Checkpoint(
                project_id="test-project",
                timestamp=f"2024-01-01T00:00:{i:02d}",
                segment_states={f"s{i}": {"sid": f"s{i}", "locked": False}},
                metadata={"total_segments": 1, "completed_segments": 0},
            )
            checkpoint_manager.save_checkpoint(checkpoint)

        # Cleanup keeping 10
        checkpoint_manager.cleanup_old_checkpoints(keep_count=10)

        checkpoints = checkpoint_manager.list_checkpoints()
        assert len(checkpoints) == 10

    def test_get_project_metadata(self, temp_project_dir: Path) -> None:
        """Test getting project metadata."""
        checkpoint_manager = CheckpointManager(temp_project_dir)

        checkpoint = Checkpoint(
            project_id="test-project",
            timestamp="2024-01-01T00:00:00",
            segment_states={},
            metadata={"title": "Test Doc", "total_segments": 5, "completed_segments": 2},
        )
        checkpoint_manager.save_checkpoint(checkpoint)

        metadata = checkpoint_manager.get_project_metadata()
        assert metadata is not None
        assert metadata["title"] == "Test Doc"
        assert metadata["total_segments"] == 5
