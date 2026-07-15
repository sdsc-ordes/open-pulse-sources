"""Pydantic model for an HF Space card."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class SpaceRecord(BaseModel):
    """Structured view of an HF Space persisted to DuckDB.

    Spaces differ from models/datasets by running an interactive demo
    (Gradio / Streamlit / Docker / static), so the schema carries
    `sdk`, `runtime_stage`, and `hardware` instead of pipeline/library.
    """

    repo_id: str
    author: str | None = None
    sha: str | None = None
    sdk: str | None = None  # "gradio" | "streamlit" | "docker" | "static"
    runtime_stage: str | None = None  # "RUNNING" | "SLEEPING" | "PAUSED" | …
    hardware: str | None = None  # "cpu-basic" | "t4-small" | …
    license: str | None = None
    likes: int = 0
    created_at: datetime | None = None
    last_modified: datetime | None = None
    tags: list[str] = []
    card_data: dict[str, Any] = {}
    raw: dict[str, Any] = {}
