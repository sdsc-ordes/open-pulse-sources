"""Config loader for the gitlab_epfl_users index."""

from __future__ import annotations

from pathlib import Path

from open_pulse_sources.index._gitlab_base.config_base import (
    GitLabIndexConfig,
    load_gitlab_config,
)

DEFAULT_CONFIG_PATH = Path("config/index/gitlab_epfl_users.yaml")

GitLabEpflUsersConfig = GitLabIndexConfig


def load_config(path: Path | None = None) -> GitLabEpflUsersConfig:
    return load_gitlab_config(
        yaml_path=path or DEFAULT_CONFIG_PATH,
        store_name="gitlab_epfl_users",
        token_env="GITLAB_EPFL_TOKEN",  # noqa: S106
    )
