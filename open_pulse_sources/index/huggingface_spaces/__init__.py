"""HuggingFace spaces index — DuckDB + Qdrant catalog of HF Space cards."""

from open_pulse_sources.index.huggingface_spaces.config import (
    HuggingFaceSpacesIndexConfig,
    load_config,
)
from open_pulse_sources.index.huggingface_spaces.models import SpaceRecord
from open_pulse_sources.index.huggingface_spaces.paths import (
    HuggingFaceSpacesPaths,
    get_huggingface_spaces_paths,
)
from open_pulse_sources.index.huggingface_spaces.storage.duckdb_store import (
    HuggingFaceSpacesStore,
)

__all__ = [
    "HuggingFaceSpacesIndexConfig",
    "HuggingFaceSpacesPaths",
    "HuggingFaceSpacesStore",
    "SpaceRecord",
    "get_huggingface_spaces_paths",
    "load_config",
]
