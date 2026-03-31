"""Tests for CLI commands."""

import os
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from aat.cli import main


@pytest.fixture
def runner() -> CliRunner:
    """Create a CLI runner for testing."""
    return CliRunner()


class TestMainCommand:
    """Test main CLI command."""

    def test_version(self, runner: CliRunner) -> None:
        """Test version flag."""
        result = runner.invoke(main, ["--version"])
        assert result.exit_code == 0
        assert "0.1.0" in result.output

    def test_help(self, runner: CliRunner) -> None:
        """Test help flag."""
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "Academic AI Translator" in result.output


class TestTranslateCommand:
    """Test translate command."""

    def test_requires_input_path(self, runner: CliRunner) -> None:
        """Test that translate requires input path."""
        result = runner.invoke(main, ["translate"])
        assert result.exit_code != 0

    def test_nonexistent_file(self, runner: CliRunner) -> None:
        """Test error on non-existent file."""
        result = runner.invoke(main, ["translate", "/nonexistent/file.docx"])
        assert result.exit_code != 0

    def test_with_existing_file(self, runner: CliRunner) -> None:
        """Test translate with a dummy file (mocked ingestion, no real API)."""
        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as f:
            f.write(b"dummy content")
            temp_path = f.name

        try:
            mock_ingestion = MagicMock()
            mock_ingestion.search_by_language.return_value = []

            with patch("aat.retrieval.ingestion.LibraryIngestion", return_value=mock_ingestion):
                result = runner.invoke(main, ["translate", temp_path])

            assert result.exit_code == 0
            assert "Translating" in result.output
        finally:
            os.unlink(temp_path)

    def test_with_target_lang(self, runner: CliRunner) -> None:
        """Test translate with target language option."""
        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as f:
            f.write(b"dummy content")
            temp_path = f.name

        try:
            mock_ingestion = MagicMock()
            mock_ingestion.search_by_language.return_value = []

            with patch("aat.retrieval.ingestion.LibraryIngestion", return_value=mock_ingestion):
                result = runner.invoke(main, ["translate", temp_path, "--to", "zh"])

            assert result.exit_code == 0
        finally:
            os.unlink(temp_path)

    def test_with_enable_web(self, runner: CliRunner) -> None:
        """Test translate with --enable-web flag."""
        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as f:
            f.write(b"dummy content")
            temp_path = f.name

        try:
            mock_ingestion = MagicMock()
            mock_ingestion.search_by_language.return_value = []

            with patch("aat.retrieval.ingestion.LibraryIngestion", return_value=mock_ingestion):
                result = runner.invoke(main, ["translate", temp_path, "--enable-web"])

            assert result.exit_code == 0
            assert "Web search enabled" in result.output
        finally:
            os.unlink(temp_path)

    def test_with_offline(self, runner: CliRunner) -> None:
        """Test translate with --offline flag."""
        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as f:
            f.write(b"dummy")
            temp_path = f.name

        try:
            mock_ingestion = MagicMock()
            mock_ingestion.search_by_language.return_value = []

            with patch("aat.retrieval.ingestion.LibraryIngestion", return_value=mock_ingestion):
                result = runner.invoke(main, ["translate", temp_path, "--offline"])

            assert result.exit_code == 0
            assert "offline mode" in result.output
        finally:
            os.unlink(temp_path)

    def test_with_ui_flag(self, runner: CliRunner) -> None:
        """Test translate with --ui flag."""
        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as f:
            f.write(b"dummy")
            temp_path = f.name

        try:
            mock_ingestion = MagicMock()
            mock_ingestion.search_by_language.return_value = []

            with patch("aat.retrieval.ingestion.LibraryIngestion", return_value=mock_ingestion):
                result = runner.invoke(main, ["translate", temp_path, "--ui"])

            assert result.exit_code == 0
            assert "aat review" in result.output
        finally:
            os.unlink(temp_path)

    def test_translate_respects_runtime_path_overrides(
        self,
        runner: CliRunner,
        monkeypatch,
        tmp_path: Path,
    ) -> None:
        """translate should use runtime path overrides for library and output storage."""
        input_file = tmp_path / "paper.docx"
        input_file.write_bytes(b"dummy")
        library_dir = tmp_path / "library-store"
        output_dir = tmp_path / "output-store"

        mock_ingestion = MagicMock()
        mock_ingestion.search_by_language.return_value = [{"text": "Example source text."}]

        mock_pipeline = MagicMock()
        mock_pipeline.run.return_value = SimpleNamespace(segments=[], translation_segments=[])

        monkeypatch.setenv("AAT_LIBRARY_DIR", str(library_dir))
        monkeypatch.setenv("AAT_OUTPUT_DIR", str(output_dir))

        with (
            patch("aat.retrieval.ingestion.LibraryIngestion", return_value=mock_ingestion) as ingestion_cls,
            patch("aat.translate.pipeline.TranslationPipeline", return_value=mock_pipeline),
        ):
            result = runner.invoke(main, ["translate", str(input_file)])

        assert result.exit_code == 0
        ingestion_cls.assert_called_once_with(library_dir)
        assert (output_dir / "paper_translated.md").exists()


class TestAddLibraryCommand:
    """Test add-library command."""

    def test_requires_path(self, runner: CliRunner) -> None:
        """Test that add-library requires a path."""
        result = runner.invoke(main, ["add-library"])
        assert result.exit_code != 0

    def test_nonexistent_path(self, runner: CliRunner) -> None:
        """Test error on non-existent path."""
        result = runner.invoke(main, ["add-library", "/nonexistent/file.pdf"])
        assert result.exit_code != 0

    def test_with_file(self, runner: CliRunner) -> None:
        """Test add-library with a file (mocked ingestion)."""
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(b"dummy pdf content")
            temp_path = f.name

        try:
            mock_ingestion = MagicMock()
            mock_ingestion.ingest_file.return_value = {
                "status": "ingested",
                "chunks_added": 5,
                "language": "en",
            }

            with patch("aat.retrieval.ingestion.LibraryIngestion", return_value=mock_ingestion):
                result = runner.invoke(main, ["add-library", temp_path])

            assert result.exit_code == 0
            assert "Adding" in result.output
        finally:
            os.unlink(temp_path)

    def test_with_directory(self, runner: CliRunner) -> None:
        """Test add-library with a directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            result = runner.invoke(main, ["add-library", temp_dir])
            assert result.exit_code == 0
            assert "Adding files from" in result.output

    def test_with_recursive_flag(self, runner: CliRunner) -> None:
        """Test add-library with --recursive flag."""
        with tempfile.TemporaryDirectory() as temp_dir:
            nested = Path(temp_dir) / "sub"
            nested.mkdir()
            (nested / "paper.pdf").write_bytes(b"dummy")

            mock_ingestion = MagicMock()
            mock_ingestion.ingest_file.return_value = {
                "status": "ingested",
                "chunks_added": 3,
                "language": "en",
            }

            with patch("aat.retrieval.ingestion.LibraryIngestion", return_value=mock_ingestion):
                result = runner.invoke(main, ["add-library", temp_dir, "--recursive"])

            assert result.exit_code == 0
            assert "Recursive mode" in result.output

    def test_respects_library_dir_override(self, runner: CliRunner, monkeypatch, tmp_path: Path) -> None:
        """AAT_LIBRARY_DIR override should be passed to LibraryIngestion."""
        input_file = tmp_path / "paper.pdf"
        input_file.write_bytes(b"dummy pdf content")
        override_dir = tmp_path / "library-store"

        mock_ingestion = MagicMock()
        mock_ingestion.ingest_file.return_value = {
            "status": "ingested",
            "chunks_added": 1,
            "language": "en",
        }

        monkeypatch.setenv("AAT_LIBRARY_DIR", str(override_dir))

        with patch("aat.retrieval.ingestion.LibraryIngestion", return_value=mock_ingestion) as ingestion_cls:
            result = runner.invoke(main, ["add-library", str(input_file)])

        assert result.exit_code == 0
        ingestion_cls.assert_called_once_with(override_dir)


class TestResumeCommand:
    """Test resume command."""

    def test_requires_project_folder(self, runner: CliRunner) -> None:
        """Test that resume requires project folder."""
        result = runner.invoke(main, ["resume"])
        assert result.exit_code != 0

    def test_with_project_folder(self, runner: CliRunner) -> None:
        """Test resume with project folder (mocked checkpoint)."""
        with tempfile.TemporaryDirectory() as temp_dir:
            mock_checkpoint = MagicMock()
            mock_checkpoint.project_id = "test-project"
            mock_checkpoint.timestamp = "2025-01-01T00:00:00"
            mock_checkpoint.segment_states = {}

            mock_manager = MagicMock()
            mock_manager.load_latest_checkpoint.return_value = mock_checkpoint
            mock_manager.get_project_metadata.return_value = {
                "total_segments": 10,
                "completed_segments": 5,
            }

            with patch("aat.storage.checkpoints.CheckpointManager", return_value=mock_manager):
                result = runner.invoke(main, ["resume", temp_dir])

            assert result.exit_code == 0
            assert "Resuming project" in result.output

    def test_resume_no_checkpoint(self, runner: CliRunner) -> None:
        """Test resume when no checkpoint exists."""
        with tempfile.TemporaryDirectory() as temp_dir:
            mock_manager = MagicMock()
            mock_manager.load_latest_checkpoint.return_value = None

            with patch("aat.storage.checkpoints.CheckpointManager", return_value=mock_manager):
                result = runner.invoke(main, ["resume", temp_dir])

            assert result.exit_code != 0


def _checkpoint_mock_with_segments():
    """Create a mock CheckpointManager that returns a checkpoint with segments."""
    segment_states = {
        "seg_1": {
            "segment": {"sid": "seg_1", "source_text": "Hello world.", "chapter_id": "ch1", "pid_list": []},
            "translation": "你好世界。",
            "locked": True,
            "state": "lock_segment",
            "uncertainties": [],
            "critic_issues": [],
            "user_comments": [],
        },
        "seg_2": {
            "segment": {"sid": "seg_2", "source_text": "Goodbye.", "chapter_id": "ch1", "pid_list": []},
            "translation": "再见。",
            "locked": True,
            "state": "lock_segment",
            "uncertainties": [],
            "critic_issues": [],
            "user_comments": [],
        },
    }
    mock_checkpoint = MagicMock()
    mock_checkpoint.project_id = "test-project"
    mock_checkpoint.timestamp = "2025-01-01T00:00:00"
    mock_checkpoint.segment_states = segment_states
    mock_checkpoint.metadata = {"title": "Test Project"}

    mock_manager = MagicMock()
    mock_manager.load_latest_checkpoint.return_value = mock_checkpoint
    return mock_manager


class TestExportCommand:
    """Test export command."""

    def test_requires_project_folder(self, runner: CliRunner) -> None:
        """Test that export requires project folder."""
        result = runner.invoke(main, ["export"])
        assert result.exit_code != 0

    def test_with_project_folder(self, runner: CliRunner) -> None:
        """Test export with project folder."""
        with tempfile.TemporaryDirectory() as temp_dir:
            mock_manager = _checkpoint_mock_with_segments()
            with patch("aat.storage.checkpoints.CheckpointManager", return_value=mock_manager):
                result = runner.invoke(main, ["export", temp_dir])
            assert result.exit_code == 0
            assert "Exporting project" in result.output

    def test_with_format_option(self, runner: CliRunner) -> None:
        """Test export with --format option."""
        with tempfile.TemporaryDirectory() as temp_dir:
            mock_manager = _checkpoint_mock_with_segments()
            with patch("aat.storage.checkpoints.CheckpointManager", return_value=mock_manager):
                result = runner.invoke(main, ["export", temp_dir, "--format", "docx"])
            assert result.exit_code == 0

    def test_with_output_option(self, runner: CliRunner) -> None:
        """Test export with --output option."""
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = os.path.join(temp_dir, "output.docx")
            mock_manager = _checkpoint_mock_with_segments()
            with patch("aat.storage.checkpoints.CheckpointManager", return_value=mock_manager):
                result = runner.invoke(main, ["export", temp_dir, "-o", output_path])
            assert result.exit_code == 0
            assert "Output file" in result.output

    def test_full_export_docx(self, runner: CliRunner) -> None:
        """Full export produces a valid .docx file."""
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = os.path.join(temp_dir, "full_export.docx")
            mock_manager = _checkpoint_mock_with_segments()
            with patch("aat.storage.checkpoints.CheckpointManager", return_value=mock_manager):
                result = runner.invoke(main, ["export", temp_dir, "-o", output_path])
            assert result.exit_code == 0
            assert os.path.exists(output_path)

    def test_export_with_bilingual_flag(self, runner: CliRunner) -> None:
        """Export with --bilingual flag runs without error."""
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = os.path.join(temp_dir, "bilingual.docx")
            mock_manager = _checkpoint_mock_with_segments()
            with patch("aat.storage.checkpoints.CheckpointManager", return_value=mock_manager):
                result = runner.invoke(main, ["export", temp_dir, "--bilingual", "-o", output_path])
            assert result.exit_code == 0

    def test_export_with_skip_global_pass(self, runner: CliRunner) -> None:
        """Export with --skip-global-pass runs without error."""
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = os.path.join(temp_dir, "skip_gp.docx")
            mock_manager = _checkpoint_mock_with_segments()
            with patch("aat.storage.checkpoints.CheckpointManager", return_value=mock_manager):
                result = runner.invoke(main, ["export", temp_dir, "--skip-global-pass", "-o", output_path])
            assert result.exit_code == 0

    def test_export_no_checkpoint(self, runner: CliRunner) -> None:
        """Export with no checkpoint should error."""
        with tempfile.TemporaryDirectory() as temp_dir:
            mock_manager = MagicMock()
            mock_manager.load_latest_checkpoint.return_value = None
            with patch("aat.storage.checkpoints.CheckpointManager", return_value=mock_manager):
                result = runner.invoke(main, ["export", temp_dir])
            assert result.exit_code != 0


class TestStatusCommand:
    """Test status command."""

    def test_status_with_project(self, runner: CliRunner) -> None:
        """Status with a valid checkpoint shows project info."""
        with tempfile.TemporaryDirectory() as temp_dir:
            mock_manager = _checkpoint_mock_with_segments()
            with patch("aat.storage.checkpoints.CheckpointManager", return_value=mock_manager):
                result = runner.invoke(main, ["status", temp_dir])
            assert result.exit_code == 0
            assert "test-project" in result.output

    def test_status_no_checkpoint(self, runner: CliRunner) -> None:
        """Status when no checkpoint exists should error."""
        with tempfile.TemporaryDirectory() as temp_dir:
            mock_manager = MagicMock()
            mock_manager.load_latest_checkpoint.return_value = None
            with patch("aat.storage.checkpoints.CheckpointManager", return_value=mock_manager):
                result = runner.invoke(main, ["status", temp_dir])
            assert result.exit_code != 0


class TestConfigCommand:
    """Test config command."""

    def test_config_shows_message(self, runner: CliRunner) -> None:
        """Test that config command shows appropriate message."""
        result = runner.invoke(main, ["config"])
        assert result.exit_code == 0


class TestInitCommand:
    """Test init command."""

    def test_init_creates_config(self, runner: CliRunner, monkeypatch, tmp_path: Path) -> None:
        """Test that init creates configuration."""
        aat_home = tmp_path / "aat-home"
        monkeypatch.setenv("AAT_HOME", str(aat_home))

        result = runner.invoke(main, ["init"])
        assert result.exit_code == 0
        assert "Configuration created" in result.output

        config_file = aat_home / "config.toml"
        assert config_file.exists()
        assert (aat_home / "library").exists()
        assert (aat_home / "output").exists()

    def test_init_overwrites_with_confirmation(self, runner: CliRunner, monkeypatch, tmp_path: Path) -> None:
        """Test that init can overwrite existing config with confirmation."""
        aat_home = tmp_path / "aat-home"
        monkeypatch.setenv("AAT_HOME", str(aat_home))

        aat_home.mkdir(exist_ok=True)
        config_file = aat_home / "config.toml"
        config_file.write_text("old config")

        result = runner.invoke(main, ["init"], input="y")
        assert result.exit_code == 0


class TestTranslateInteractiveFlag:
    """Test --interactive flag on translate command."""

    def test_translate_accepts_interactive_flag(self, runner: CliRunner) -> None:
        """translate --help should mention --interactive."""
        result = runner.invoke(main, ["translate", "--help"])
        assert result.exit_code == 0
        assert "--interactive" in result.output


class TestReviseCommand:
    """Test 'aat revise' command."""

    def test_revise_command_exists(self, runner: CliRunner) -> None:
        """'aat revise --help' should succeed."""
        result = runner.invoke(main, ["revise", "--help"])
        assert result.exit_code == 0
        assert "Revise segments" in result.output

    def test_revise_requires_project_folder(self, runner: CliRunner) -> None:
        """'aat revise' with no args should fail."""
        result = runner.invoke(main, ["revise"])
        assert result.exit_code != 0

    def test_revise_nonexistent_folder(self, runner: CliRunner) -> None:
        """'aat revise /nonexistent' should fail."""
        result = runner.invoke(main, ["revise", "/nonexistent_dir_12345"])
        assert result.exit_code != 0

    def test_revise_all_with_checkpoint(self, runner: CliRunner, tmp_path: Path) -> None:
        """'aat revise --all' on a project with feedback should process segments."""
        from tests.test_ui.test_project_loader import _create_test_checkpoint

        project_dir = _create_test_checkpoint(tmp_path, [
            {
                "sid": "s1",
                "source_text": "Test.",
                "translation": "测试。",
                "user_comments": [{"text": "fix this", "timestamp": "now"}],
                "state": "user_feedback_wait",
            },
        ])

        result = runner.invoke(main, ["revise", str(project_dir), "--all"])
        assert result.exit_code == 0
        assert "Revised" in result.output


class TestSetPreferenceCommand:
    """Test 'aat set-preference' command."""

    def test_set_preference_command_exists(self, runner: CliRunner) -> None:
        """'aat set-preference --help' should succeed."""
        result = runner.invoke(main, ["set-preference", "--help"])
        assert result.exit_code == 0
        assert "Set project-level" in result.output

    def test_set_preference_term(self, runner: CliRunner, tmp_path: Path) -> None:
        """'aat set-preference --term' should add terminology override."""
        from aat.storage.checkpoints import CheckpointManager
        from tests.test_ui.test_project_loader import _create_test_checkpoint

        project_dir = _create_test_checkpoint(tmp_path, [
            {"sid": "s1", "source_text": "Test.", "translation": "测试。"},
        ])

        result = runner.invoke(main, ["set-preference", str(project_dir), "--term", "entropy=熵"])
        assert result.exit_code == 0

        cm = CheckpointManager(project_dir)
        prefs = cm.get_project_preferences()
        assert "entropy" in prefs.get("terminology_overrides", {})

    def test_set_preference_tone(self, runner: CliRunner, tmp_path: Path) -> None:
        """'aat set-preference --tone academic' should set style preference."""
        from aat.storage.checkpoints import CheckpointManager
        from tests.test_ui.test_project_loader import _create_test_checkpoint

        project_dir = _create_test_checkpoint(tmp_path, [
            {"sid": "s1", "source_text": "Test.", "translation": "测试。"},
        ])

        result = runner.invoke(main, ["set-preference", str(project_dir), "--tone", "academic"])
        assert result.exit_code == 0

        cm = CheckpointManager(project_dir)
        prefs = cm.get_project_preferences()
        assert prefs.get("tone") == "academic"


class TestReviewCommand:
    """Test 'aat review' command."""

    def test_review_requires_folder(self, runner: CliRunner) -> None:
        """'aat review' with no args should fail."""
        result = runner.invoke(main, ["review"])
        assert result.exit_code != 0

    def test_review_nonexistent_folder(self, runner: CliRunner) -> None:
        """'aat review /nonexistent' should fail."""
        result = runner.invoke(main, ["review", "/nonexistent_dir_12345"])
        assert result.exit_code != 0

    def test_review_supports_host_and_no_browser(self, runner: CliRunner, tmp_path: Path) -> None:
        """Container-friendly review flags should suppress browser launch and pass host through."""
        with (
            patch("aat.ui.server.create_app") as create_app_mock,
            patch("aat.ui.server.app", new=MagicMock(name="app")),
            patch("webbrowser.open") as open_mock,
            patch("uvicorn.run") as uvicorn_run_mock,
        ):
            result = runner.invoke(
                main,
                ["review", str(tmp_path), "--host", "0.0.0.0", "--port", "9000", "--no-browser"],
            )

        assert result.exit_code == 0
        create_app_mock.assert_called_once_with(tmp_path)
        open_mock.assert_not_called()
        uvicorn_run_mock.assert_called_once()
        _, kwargs = uvicorn_run_mock.call_args
        assert kwargs["host"] == "0.0.0.0"
        assert kwargs["port"] == 9000
