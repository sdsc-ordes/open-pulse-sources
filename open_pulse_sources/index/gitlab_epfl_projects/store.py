"""DuckDB store accessor for the gitlab_epfl_projects index."""

from __future__ import annotations

from open_pulse_sources.index._gitlab_base.project_store import GitLabProjectStore
from open_pulse_sources.index.gitlab_epfl_projects.paths import (
    get_gitlab_epfl_projects_paths,
)


def open_store() -> GitLabProjectStore:
    """Open (and bootstrap) the gitlab_epfl_projects DuckDB store."""
    return GitLabProjectStore.open(get_gitlab_epfl_projects_paths().duckdb_path)
