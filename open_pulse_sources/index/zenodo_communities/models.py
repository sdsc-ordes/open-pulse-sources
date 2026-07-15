"""Pydantic models for the zenodo_communities index."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class CommunityRecord(BaseModel):
    """One row of the `communities` table.

    `community_id` is the canonical IRI for the community at its source
    (e.g. `https://zenodo.org/communities/epfl-chili`). The
    `open_pulse_sources.index.zenodo_communities.iri.canonical_community_id(source, slug)`
    helper centralises the mapping; legacy `zenodo:<slug>` rows are
    migrated in-place by `bootstrap()`.
    """

    community_id: str
    source: str                       # 'zenodo', 'github', ...
    source_slug: str                  # raw slug from the source platform
    parent_org: str | None = None  # 'epfl' | 'ethz' | 'cern' | 'cern_openlab'
    title: str | None = None
    description: str | None = None
    url: str | None = None
    visibility: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    curator_names: list[str] = Field(default_factory=list)
    member_count: int | None = None
    record_count: int | None = None
    keywords: list[str] = Field(default_factory=list)
    raw: dict[str, Any] = Field(default_factory=dict)
