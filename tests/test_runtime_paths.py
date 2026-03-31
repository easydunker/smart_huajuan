"""Tests for runtime path helpers."""

from pathlib import Path

from aat import runtime_paths


class TestRuntimePaths:
    """Verify runtime path defaults and env overrides."""

    def test_defaults_follow_home_and_cwd(self, monkeypatch, tmp_path: Path) -> None:
        """Default paths should derive from the local home and cwd."""
        fake_home = tmp_path / "home"
        fake_cwd = tmp_path / "workspace"

        monkeypatch.delenv("AAT_HOME", raising=False)
        monkeypatch.delenv("AAT_LIBRARY_DIR", raising=False)
        monkeypatch.delenv("AAT_OUTPUT_DIR", raising=False)
        monkeypatch.delenv("AAT_PROJECTS_DIR", raising=False)
        monkeypatch.setattr(runtime_paths.Path, "home", lambda: fake_home)
        monkeypatch.setattr(runtime_paths.Path, "cwd", lambda: fake_cwd)

        assert runtime_paths.get_aat_home() == fake_home / ".aat"
        assert runtime_paths.get_library_dir() == fake_home / ".aat" / "library"
        assert runtime_paths.get_output_dir() == fake_home / ".aat" / "output"
        assert runtime_paths.get_projects_dir() == fake_cwd / "projects"
        assert runtime_paths.get_config_path() == fake_home / ".aat" / "config.toml"

    def test_explicit_env_overrides_take_precedence(self, monkeypatch, tmp_path: Path) -> None:
        """Specific env vars should override every runtime path."""
        aat_home = tmp_path / "custom-home"
        library_dir = tmp_path / "custom-library"
        output_dir = tmp_path / "custom-output"
        projects_dir = tmp_path / "custom-projects"

        monkeypatch.setenv("AAT_HOME", str(aat_home))
        monkeypatch.setenv("AAT_LIBRARY_DIR", str(library_dir))
        monkeypatch.setenv("AAT_OUTPUT_DIR", str(output_dir))
        monkeypatch.setenv("AAT_PROJECTS_DIR", str(projects_dir))

        assert runtime_paths.get_aat_home() == aat_home
        assert runtime_paths.get_library_dir() == library_dir
        assert runtime_paths.get_output_dir() == output_dir
        assert runtime_paths.get_projects_dir() == projects_dir

    def test_home_override_flows_into_default_child_directories(self, monkeypatch, tmp_path: Path) -> None:
        """AAT_HOME should influence default library, output, and config paths."""
        aat_home = tmp_path / "alt-home"

        monkeypatch.setenv("AAT_HOME", str(aat_home))
        monkeypatch.delenv("AAT_LIBRARY_DIR", raising=False)
        monkeypatch.delenv("AAT_OUTPUT_DIR", raising=False)

        assert runtime_paths.get_library_dir() == aat_home / "library"
        assert runtime_paths.get_output_dir() == aat_home / "output"
        assert runtime_paths.get_config_path() == aat_home / "config.toml"
