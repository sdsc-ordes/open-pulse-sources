"""Config loader for the huggingface_models index."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from open_pulse_sources.index._huggingface_base.config_base import (
    HFEntityIndexConfigBase,
    load_hf_entity_config,
)
from open_pulse_sources.index.huggingface_models.paths import get_huggingface_models_paths

DEFAULT_CONFIG_PATH = Path("config/index/huggingface_models.yaml")

HuggingFaceModelsIndexConfig = HFEntityIndexConfigBase


def load_config(path: Optional[Path] = None) -> HuggingFaceModelsIndexConfig:
    return load_hf_entity_config(
        yaml_path=path or DEFAULT_CONFIG_PATH,
        paths=get_huggingface_models_paths(),
    )
