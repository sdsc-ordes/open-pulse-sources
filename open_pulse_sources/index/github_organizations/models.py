"""Pydantic model for a GitHub organization card."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class OrgRecord(BaseModel):
    """Structured view of a GitHub organization persisted to DuckDB.

    `login` is the org handle (e.g. `EPFL-ENAC`). Field set is the
    intersection of `/orgs/{org}` and `/users/{login}` payloads — every
    org GitHub returns has at minimum `login`, `id`, `description`,
    `public_repos`, `followers`. Optional `is_verified` is org-only.
    """

    login: str
    github_id: int | None = None
    node_id: str | None = None
    name: str | None = None
    description: str | None = None
    blog: str | None = None
    location: str | None = None
    email: str | None = None
    twitter_username: str | None = None
    company: str | None = None
    public_repos: int = 0
    public_gists: int = 0
    followers: int = 0
    following: int = 0
    is_verified: bool | None = None
    has_organization_projects: bool | None = None
    has_repository_projects: bool | None = None
    account_type: str | None = None  # "Organization"
    avatar_url: str | None = None
    html_url: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    raw: dict[str, Any] = {}
