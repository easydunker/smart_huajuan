"""Tests for checkpoint system."""

import json
import tempfile
from pathlib import Path

import pytest

from aat.storage.checkpoints import (
    Checkpoint,
    CheckpointManager,
    create_checkpoint_manager,
)
from aat.runtime_paths import get_projects_dir
from aat.storage.models import (
    DocumentModel,
    Paragraph,
    Section,
    Segment,
    TranslationProject,
    TranslationSegment,
    SegmentState,
)

from tests.test_ui.test_project_loader import _create_test_checkpoint


@pytest.fixture
def temp_project_dir() -> Path:
    """Create a temporary project directory."""
    return Path(tempfile.mkdtemp())


@pytest.fixture
def sample_project() -> TranslationProject:
    """Create a sample translation project."""
    doc = DocumentModel.create()
    doc.title = "Test Document"
    doc.sections = [
        Section(
            heading="Introduction",
            paragraphs=[
                Paragraph(pid="p1", text="Test paragraph one."),
                Paragraph(pid="p2", text="Test paragraph two."),
            ],
        )
    ]
    doc.references = []
    doc.citations = []

    project = TranslationProject.create(doc)
    project.segments = [
        TranslationSegment(
            segment=Segment(
                sid="s1",
                pid_list=["p1"],
                source_text="Test paragraph one.",
            ),
            state=SegmentState.ASSEMBLE_CONTEXT,
            translation="Translated one.",
        ),
        TranslationSegment(
            segment=Segment(
                sid="s2",
                pid_list=["p2"],
                source_text="Test paragraph two.",
            ),
            state=SegmentState.LOCK_SEGMENT,
            translation="Translated two.",
        ),
    ]
    project.segments[1].locked = True
    return project


class TestCheckpoint:
    """Test Checkpoint dataclass."""

    def test_create_checkpoint(self, temp_project_dir) -> None:
        """Test creating a checkpoint from project."""
        from aat.storage.models import DocumentModel, Section, Paragraph, Segment
        doc = DocumentModel.create()
        doc.title = "Test Document"
        doc.sections = [
            Section(heading="Introduction", paragraphs=[
                Paragraph(pid="p1", text="First paragraph with citation (Smith, 2021)."),
            ]),
            Section(heading=None, paragraphs=[
                Paragraph(pid="p2", text="Second paragraph."),
            ]),
        ]
        project = TranslationProject.create(doc)
        # Add segments to project so checkpoint can capture them
        project.segments = [
            TranslationSegment(
                segment=Segment(
                    sid="s1",
                    pid_list=["p1"],
                    source_text="First paragraph with citation (Smith, 2021).",
                ),
                state=SegmentState.ASSEMBLE_CONTEXT,
                translation="Translated one.",
            ),
            TranslationSegment(
                segment=Segment(
                    sid="s2",
                    pid_list=["p2"],
                    source_text="Second paragraph.",
                ),
                state=SegmentState.LOCK_SEGMENT,
                translation="Translated two.",
            ),
        ]
        project.segments[1].locked = True

        checkpoint = Checkpoint.create(project)

        assert checkpoint.project_id == project.project_id
        assert checkpoint.timestamp
        assert len(checkpoint.segment_states) == 2
        assert checkpoint.metadata["title"] == "Test Document"
        assert checkpoint.metadata["total_segments"] == 2
        assert checkpoint.metadata["completed_segments"] == 1

    def test_to_json_and_from_json(self, temp_project_dir) -> None:
        """Test JSON serialization/deserialization."""
        from aat.storage.models import DocumentModel, Section, Paragraph, Segment
        doc = DocumentModel.create()
        doc.title = "Test Document"
        doc.sections = [
            Section(heading="Introduction", paragraphs=[
                Paragraph(pid="p1", text="First paragraph with citation (Smith, 2021)."),
            ]),
            Section(heading=None, paragraphs=[
                Paragraph(pid="p2", text="Second paragraph."),
            ]),
        ]
        project = TranslationProject.create(doc)
        project.segments = [
            TranslationSegment(
                segment=Segment(
                    sid="s1",
                    pid_list=["p1"],
                    source_text="First paragraph with citation (Smith, 2021).",
                ),
                state=SegmentState.ASSEMBLE_CONTEXT,
                translation="Translated one.",
            ),
            TranslationSegment(
                segment=Segment(
                    sid="s2",
                    pid_list=["p2"],
                    source_text="Second paragraph.",
                ),
                state=SegmentState.LOCK_SEGMENT,
                translation="Translated two.",
            ),
        ]
        project.segments[1].locked = True
        checkpoint = Checkpoint.create(project)

        json_str = checkpoint.to_json()
        assert isinstance(json_str, str)

        restored = Checkpoint.from_json(json_str)
        assert restored.project_id == checkpoint.project_id
        assert restored.timestamp == checkpoint.timestamp
        assert restored.segment_states == checkpoint.segment_states


class TestCheckpointManager:
    """Test CheckpointManager."""

    def test_init_creates_directory(self, temp_project_dir) -> None:
        """Test initialization creates checkpoints directory."""
        manager = CheckpointManager(temp_project_dir)

        checkpoints_dir = temp_project_dir / "checkpoints"
        assert checkpoints_dir.exists()
        assert checkpoints_dir.is_dir()

    def test_save_checkpoint(self, temp_project_dir) -> None:
        """Test saving a checkpoint."""
        manager = CheckpointManager(temp_project_dir)
        from aat.storage.models import DocumentModel, Section, Paragraph
        doc = DocumentModel.create()
        doc.title = "Test Document"
        doc.sections = [
            Section(heading="Introduction", paragraphs=[
                Paragraph(pid="p1", text="First paragraph with citation (Smith, 2021)."),
            ]),
            Section(heading=None, paragraphs=[
                Paragraph(pid="p2", text="Second paragraph."),
            ]),
        ]
        project = TranslationProject.create(doc)
        checkpoint = Checkpoint.create(project)

        filepath = manager.save_checkpoint(checkpoint)

        assert filepath.exists()
        assert filepath.parent == temp_project_dir / "checkpoints"
        assert filepath.name.startswith("checkpoint_")
        assert filepath.suffix == ".json"

    def test_load_latest_checkpoint(self, temp_project_dir, sample_project) -> None:
        """Test loading most recent checkpoint."""
        manager = CheckpointManager(temp_project_dir)
        checkpoint = Checkpoint.create(sample_project)

        manager.save_checkpoint(checkpoint)

        loaded = manager.load_latest_checkpoint()

        assert loaded is not None
        assert loaded.project_id == checkpoint.project_id
        assert loaded.segment_states == checkpoint.segment_states

    def test_load_no_checkpoints_returns_none(self, temp_project_dir) -> None:
        """Test loading when no checkpoints exist."""
        manager = CheckpointManager(temp_project_dir)

        loaded = manager.load_latest_checkpoint()
        assert loaded is None

    def test_list_checkpoints(self, temp_project_dir, sample_project) -> None:
        """Test listing all checkpoints."""
        manager = CheckpointManager(temp_project_dir)

        # Save multiple checkpoints
        for i in range(3):
            sample_project.project_id = f"test-{i}"
            checkpoint = Checkpoint.create(sample_project)
            manager.save_checkpoint(checkpoint)

        checkpoints = manager.list_checkpoints()

        assert len(checkpoints) == 3
        assert all(c.suffix == ".json" for c in checkpoints)

    def test_list_checkpoints_sorted(self, temp_project_dir, sample_project) -> None:
        """Test that checkpoints are sorted by modification time (newest first)."""
        manager = CheckpointManager(temp_project_dir)

        # Save checkpoints with delays
        for i in range(3):
            import time
            sample_project.project_id = f"test-{i}"
            checkpoint = Checkpoint.create(sample_project)
            manager.save_checkpoint(checkpoint)
            time.sleep(0.1)  # Small delay to ensure different mtimes

        checkpoints = manager.list_checkpoints()

        # Check that they're sorted (newest first)
        mtimes = [c.stat().st_mtime for c in checkpoints]
        assert mtimes == sorted(mtimes, reverse=True)

    def test_cleanup_old_checkpoints(self, temp_project_dir, sample_project) -> None:
        """Test cleanup of old checkpoints."""
        manager = CheckpointManager(temp_project_dir)

        # Save more than 10 checkpoints
        for i in range(15):
            sample_project.project_id = f"test-{i}"
            checkpoint = Checkpoint.create(sample_project)
            manager.save_checkpoint(checkpoint)

        # Cleanup keeping 10
        manager.cleanup_old_checkpoints(keep_count=10)

        checkpoints = manager.list_checkpoints()
        assert len(checkpoints) == 10

    def test_get_project_metadata(self, temp_project_dir, sample_project) -> None:
        """Test getting project metadata."""
        manager = CheckpointManager(temp_project_dir)
        checkpoint = Checkpoint.create(sample_project)

        manager.save_checkpoint(checkpoint)

        metadata = manager.get_project_metadata()

        assert metadata is not None
        assert metadata["title"] == "Test Document"
        assert metadata["total_segments"] == 2

    def test_get_project_metadata_no_checkpoint(self, temp_project_dir) -> None:
        """Test getting metadata when no checkpoint exists."""
        manager = CheckpointManager(temp_project_dir)

        metadata = manager.get_project_metadata()
        assert metadata is None


class TestUserCommentsConsistency:
    """Tests exposing user_comments type mismatch between model and checkpoint."""

    def test_add_comment_schema_consistency(self, tmp_path: Path) -> None:
        """Comments added via checkpoint should be dicts with 'text' and 'timestamp'."""
        project_dir = _create_test_checkpoint(tmp_path, [
            {"sid": "s1", "user_comments": []},
        ])
        cm = CheckpointManager(project_dir)

        cm.add_comment("s1", "test")
        reloaded = cm.load_latest_checkpoint()
        comments = reloaded.segment_states["s1"]["user_comments"]
        assert len(comments) == 1
        assert isinstance(comments[0], dict)
        assert "text" in comments[0]
        assert "timestamp" in comments[0]

    def test_add_comment_to_existing_string_comments(self, tmp_path: Path) -> None:
        """Old string-format comments should be migrated to dict format."""
        project_dir = _create_test_checkpoint(tmp_path, [
            {"sid": "s1", "user_comments": ["old comment"]},
        ])
        cm = CheckpointManager(project_dir)

        cm.add_comment("s1", "new")
        reloaded = cm.load_latest_checkpoint()
        comments = reloaded.segment_states["s1"]["user_comments"]
        assert all(isinstance(c, dict) for c in comments)

    def test_user_comments_type_in_model_matches_checkpoint(self) -> None:
        """TranslationSegment.user_comments type annotation should allow dict format."""
        import typing
        hints = typing.get_type_hints(TranslationSegment)
        annotation = hints["user_comments"]
        annotation_str = str(annotation)
        assert "dict" in annotation_str, (
            f"user_comments type is {annotation_str}, should include dict"
        )


class TestCheckpointPreferences:
    """Tests for preferences field and checkpoint methods."""

    def test_checkpoint_has_preferences_field(self) -> None:
        """Checkpoint should have a preferences field defaulting to {}."""
        cp = Checkpoint(
            project_id="test", timestamp="now",
            segment_states={}, metadata={},
        )
        assert cp.preferences == {}

    def test_checkpoint_to_json_includes_preferences(self, tmp_path: Path) -> None:
        """to_json should include 'preferences' key."""
        cp = Checkpoint(
            project_id="test", timestamp="now",
            segment_states={}, metadata={},
            preferences={"terminology_overrides": {"entropy": "熵"}},
        )
        import json
        data = json.loads(cp.to_json())
        assert "preferences" in data
        assert data["preferences"]["terminology_overrides"]["entropy"] == "熵"

    def test_checkpoint_from_json_reads_preferences(self) -> None:
        """Roundtrip: to_json then from_json preserves preferences."""
        cp = Checkpoint(
            project_id="test", timestamp="now",
            segment_states={}, metadata={},
            preferences={"style": "formal"},
        )
        restored = Checkpoint.from_json(cp.to_json())
        assert restored.preferences == {"style": "formal"}

    def test_checkpoint_from_json_backward_compat(self) -> None:
        """Old JSON without 'preferences' key should load with preferences={}."""
        import json
        old_json = json.dumps({
            "project_id": "test",
            "timestamp": "now",
            "segment_states": {},
            "metadata": {},
        })
        cp = Checkpoint.from_json(old_json)
        assert cp.preferences == {}


class TestCheckpointNewMethods:
    """Tests for new checkpoint manager methods."""

    def test_request_revision_sets_flags(self, tmp_path: Path) -> None:
        """request_revision should set revision_requested, state, and unlock."""
        project_dir = _create_test_checkpoint(tmp_path, [
            {"sid": "s1", "locked": True, "state": "lock_segment"},
        ])
        cm = CheckpointManager(project_dir)

        result = cm.request_revision("s1")
        assert result is True

        reloaded = cm.load_latest_checkpoint()
        seg = reloaded.segment_states["s1"]
        assert seg["revision_requested"] is True
        assert seg["state"] == "user_feedback_wait"
        assert seg["locked"] is False

    def test_add_structured_feedback_appends(self, tmp_path: Path) -> None:
        """add_structured_feedback should append one feedback item."""
        project_dir = _create_test_checkpoint(tmp_path, [{"sid": "s1"}])
        cm = CheckpointManager(project_dir)

        result = cm.add_structured_feedback("s1", "OMISSION", "Missing sentence")
        assert result is True

        reloaded = cm.load_latest_checkpoint()
        fb = reloaded.segment_states["s1"]["structured_feedback"]
        assert len(fb) == 1
        assert fb[0]["category"] == "OMISSION"
        assert fb[0]["detail"] == "Missing sentence"

    def test_add_structured_feedback_multiple(self, tmp_path: Path) -> None:
        """Multiple calls should accumulate feedback items."""
        project_dir = _create_test_checkpoint(tmp_path, [{"sid": "s1"}])
        cm = CheckpointManager(project_dir)

        cm.add_structured_feedback("s1", "OMISSION", "Missing sentence")
        cm.add_structured_feedback("s1", "TONE_ISSUE", "Too informal")

        reloaded = cm.load_latest_checkpoint()
        fb = reloaded.segment_states["s1"]["structured_feedback"]
        assert len(fb) == 2

    def test_set_project_preferences_roundtrip(self, tmp_path: Path) -> None:
        """set then get project preferences should roundtrip."""
        project_dir = _create_test_checkpoint(tmp_path, [{"sid": "s1"}])
        cm = CheckpointManager(project_dir)

        prefs = {"terminology_overrides": {"entropy": "熵"}}
        result = cm.set_project_preferences(prefs)
        assert result is True

        loaded = cm.get_project_preferences()
        assert loaded["terminology_overrides"]["entropy"] == "熵"

    def test_get_project_preferences_empty_default(self, tmp_path: Path) -> None:
        """No preferences set should return {}."""
        project_dir = _create_test_checkpoint(tmp_path, [{"sid": "s1"}])
        cm = CheckpointManager(project_dir)

        prefs = cm.get_project_preferences()
        assert prefs == {}


class TestCreateCheckpointManager:
    """Test create_checkpoint_manager factory function."""

    def test_without_project_id(self) -> None:
        """Test creating manager without project ID (uses temp dir)."""
        manager = create_checkpoint_manager()

        # Should create a temp directory
        assert manager.project_dir.exists()

    def test_with_project_id(self, monkeypatch, tmp_path: Path) -> None:
        """Test creating manager with project ID."""
        project_id = "test-project-123"
        projects_dir = tmp_path / "custom-projects"
        monkeypatch.setenv("AAT_PROJECTS_DIR", str(projects_dir))

        expected_project_dir = get_projects_dir() / project_id

        manager = create_checkpoint_manager(project_id)

        assert manager.project_dir == expected_project_dir
