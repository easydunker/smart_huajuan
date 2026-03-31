"""Runtime path helpers for local and containerized AAT workflows."""

from __future__ import annotations

import os
from pathlib import Path


def _path_from_env(env_var: str, default: Path) -> Path:
    """Resolve a path from the environment with a sensible default."""
    value = os.getenv(env_var)
    if not value:
        return default
    return Path(value).expanduser()


def get_aat_home() -> Path:
    """Return the base directory for persistent AAT user data."""
    return _path_from_env("AAT_HOME", Path.home() / ".aat")


def get_library_dir() -> Path:
    """Return the persistent local library directory."""
    return _path_from_env("AAT_LIBRARY_DIR", get_aat_home() / "library")


def get_output_dir() -> Path:
    """Return the directory used for generated CLI outputs."""
    return _path_from_env("AAT_OUTPUT_DIR", get_aat_home() / "output")


def get_projects_dir() -> Path:
    """Return the default parent directory for generated project folders."""
    return _path_from_env("AAT_PROJECTS_DIR", Path.cwd() / "projects")


def get_config_path() -> Path:
    """Return the path to the main CLI configuration file."""
    return get_aat_home() / "config.toml"
