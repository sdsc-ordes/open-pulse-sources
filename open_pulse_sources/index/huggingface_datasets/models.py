"""Pydantic model for an HF dataset card."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class DatasetRecord(BaseModel):
    """Structured view of an HF dataset persisted to DuckDB.

    Differs from ModelRecord by carrying citation metadata (BibTeX text,
    paperswithcode URL, and DOIs extracted from the citation block) and
    the structured `dataset_info` block instead of pipeline/library
    fields.
    """

    repo_id: str
    author: str | None = None
    sha: str | None = None
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
    dataset_info: dict[str, Any] = {}
    citation_text: str | None = None
    paperswithcode_url: str | None = None
    citation_dois: list[str] = []
    raw: dict[str, Any] = {}
