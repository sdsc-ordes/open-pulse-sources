"""Pydantic model for an HF model card."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class ModelRecord(BaseModel):
    """Structured view of an HF model persisted to DuckDB.

    ``repo_id`` is the canonical URL (https://huggingface.co/<repo_id>).
    Mirrors the schema columns in ``storage/schema.sql``.
    """

    repo_id: str
    author: str | None = None
    sha: str | None = None
    pipeline_tag: str | None = None
    library_name: str | None = None
    license: str | None = None
    downloads: int = 0
    downloads_all_time: int = 0
    likes: int = 0
    gated: bool | None = None
    private: bool | None = None
    created_at: datetime | None = None
    last_modified: datetime | None = None
    tags: list[str] = []
    card_data: dict[str, Any] = {}
    base_models: list[str] = []
    # arXiv DOIs derived from `arxiv:<id>` tags, in canonical URL form
    # `https://doi.org/10.48550/arXiv.<id>`.
    arxiv_dois: list[str] = []
    raw: dict[str, Any] = {}
