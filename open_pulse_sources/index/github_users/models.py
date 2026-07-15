"""Pydantic model for a GitHub user card."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class UserRecord(BaseModel):
    """Structured view of a GitHub user persisted to DuckDB.

    `login` is the natural primary key. `github_id` is the numeric
    user id GitHub assigns (stable across login renames).
    """

    login: str
    github_id: int | None = None
    node_id: str | None = None
    name: str | None = None
    bio: str | None = None
    company: str | None = None
    blog: str | None = None
    location: str | None = None
    email: str | None = None
    twitter_username: str | None = None
    hireable: bool | None = None
    public_repos: int = 0
    public_gists: int = 0
    followers: int = 0
    following: int = 0
    account_type: str | None = None  # "User" (vs Organization)
    avatar_url: str | None = None
    html_url: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    raw: dict[str, Any] = {}
