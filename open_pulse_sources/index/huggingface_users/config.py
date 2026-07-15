"""Config loader for the huggingface_users index."""

from __future__ import annotations

from pathlib import Path

from open_pulse_sources.index._huggingface_base.config_base import (
    HFEntityIndexConfigBase,
    load_hf_entity_config,
)
from open_pulse_sources.index.huggingface_users.paths import get_huggingface_users_paths

DEFAULT_CONFIG_PATH = Path("config/index/huggingface_users.yaml")

HuggingFaceUsersIndexConfig = HFEntityIndexConfigBase


def load_config(path: Path | None = None) -> HuggingFaceUsersIndexConfig:
    return load_hf_entity_config(
        yaml_path=path or DEFAULT_CONFIG_PATH,
        paths=get_huggingface_users_paths(),
    )
