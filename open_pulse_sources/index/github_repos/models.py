"""Pydantic models for the GitHub index module.

`RepoRecord` is the structured view we persist into DuckDB. `raw` carries
the unparsed REST `repos/{owner}/{name}` payload for debugging and future
field additions without re-ingesting.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class ContributorEntry(BaseModel):
    login: str
    contributions: int = 0


class RepoRecord(BaseModel):
    repo_id: str  # canonical URL: https://github.com/<owner>/<name>
    owner: str
    name: str
    default_branch: str | None = None
    description: str | None = None
    homepage: str | None = None
    primary_language: str | None = None
    languages: dict[str, int] = {}
    topics: list[str] = []
    license_spdx: str | None = None
    is_fork: bool = False
    is_archived: bool = False
    is_private: bool = False
    stargazers_count: int = 0
    forks_count: int = 0
    watchers_count: int = 0
    open_issues_count: int = 0
    size_kb: int = 0
    created_at: datetime | None = None
    pushed_at: datetime | None = None
    readme_path: str | None = None
    readme_text: str | None = None
    contributors: list[ContributorEntry] = []
    raw: dict[str, Any] = {}
