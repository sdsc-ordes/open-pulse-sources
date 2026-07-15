"""Pydantic model for an HF user namespace card.

Named ``HFUserRecord`` (not ``UserRecord``) to disambiguate from
``open_pulse_sources.index.github_users.models.UserRecord`` in cross-module imports.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class HFUserRecord(BaseModel):
    """Structured view of an HF user namespace persisted to DuckDB.

    HF's namespace overview returns a user's display name, bio, avatar,
    and counts of public models/datasets/spaces under that namespace.
    """

    slug: str  # namespace handle, e.g. "ylecun"
    fullname: str | None = None  # display name
    details: str | None = None   # bio
    avatar_url: str | None = None
    num_models: int = 0
    num_datasets: int = 0
    num_spaces: int = 0
    num_followers: int = 0
    raw: dict[str, Any] = {}
