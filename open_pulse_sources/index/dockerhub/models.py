"""Pydantic models for the Docker Hub index module.

`DockerhubRepoRecord` is the structured view we persist into DuckDB.
`raw` carries the unparsed `/v2/repositories/{namespace}/{name}` payload
for debugging and future field additions without re-ingesting.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class DockerhubRepoRecord(BaseModel):
    repo_id: str  # canonical URL: https://hub.docker.com/(r/<ns>/<name> | _/<name>)
    namespace: str
    name: str
    description: str | None = None       # short tagline
    full_description: str | None = None  # README markdown
    is_official: bool = False
    is_automated: bool = False
    is_private: bool = False
    star_count: int = 0
    pull_count: int = 0
    status: str | None = None
    last_updated: datetime | None = None
    date_registered: datetime | None = None
    tags: list[str] = []
    raw: dict[str, Any] = {}
