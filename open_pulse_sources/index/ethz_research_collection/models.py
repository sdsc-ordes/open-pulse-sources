"""Pydantic models passed between pipeline stages.

The LanceDB row shapes live in `store.py` (PyArrow schemas, not Pydantic) so
the schemas aren't duplicated; these models cover on-disk JSON/JSONL and
in-memory transfer between stages.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class DiscoverState(BaseModel):
    """Persisted under `discover_state.json` for resumability."""

    per_term_cursor: dict[str, int] = Field(default_factory=dict)
    per_term_total: dict[str, int] = Field(default_factory=dict)
    completed: dict[str, bool] = Field(default_factory=dict)
    last_run_iso: str | None = None


class MatchRecord(BaseModel):
    """One line in `matches.jsonl`."""

    uuid: str
    matched_urls: list[str] = Field(default_factory=list)
    counts_by_host: dict[str, int] = Field(default_factory=dict)


class RelationRecord(BaseModel):
    """One line in `relations.jsonl`."""

    article_uuid: str
    person_uuids: list[str] = Field(default_factory=list)
    org_uuids: list[str] = Field(default_factory=list)


class ChunkRecord(BaseModel):
    """In-memory chunk before insertion into LanceDB."""

    chunk_id: str
    article_uuid: str
    chunk_index: int
    text: str
    title: str | None = None
    abstract: str | None = None
    authors: list[str] = Field(default_factory=list)
    author_uuids: list[str] = Field(default_factory=list)
    doi: str | None = None
    publication_date: str | None = None
    year: int | None = None
    publication_type: str | None = None
    language: str | None = None
    subjects: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    lab: str | None = None
    lab_uuid: str | None = None
    org_uuids: list[str] = Field(default_factory=list)
    research_collection_url: str | None = None
    matched_urls: list[str] = Field(default_factory=list)


class ArticleRecord(BaseModel):
    """One row of `ethz_research_collection_articles`."""

    article_uuid: str
    title: str | None = None
    abstract: str | None = None
    keywords: list[str] = Field(default_factory=list)
    subjects: list[str] = Field(default_factory=list)
    authors: list[str] = Field(default_factory=list)
    author_uuids: list[str] = Field(default_factory=list)
    doi: str | None = None
    publication_date: str | None = None
    year: int | None = None
    publication_type: str | None = None
    language: str | None = None
    journal: str | None = None
    journal_uuid: str | None = None
    # ETH RC's `ethz.*` extension fields. None of these are present on
    # EPFL Infoscience records (which uses different namespaces); they are
    # only populated when the source DSpace deployment is the ETH Research
    # Collection.
    scopus_id: str | None = None
    wos_id: str | None = None
    journal_volume: str | None = None
    journal_issue: str | None = None
    pages_start: str | None = None
    journal_abbreviated: str | None = None
    publisher: str | None = None
    issn: str | None = None
    handle_uri: str | None = None
    lab: str | None = None
    lab_uuid: str | None = None
    org_uuids: list[str] = Field(default_factory=list)
    research_collection_url: str | None = None
    matched_urls: list[str] = Field(default_factory=list)
    chunk_count: int = 0


class PersonRecord(BaseModel):
    """One row of `ethz_research_collection_persons`."""

    person_uuid: str
    name: str | None = None
    given_name: str | None = None
    family_name: str | None = None
    orcid: str | None = None
    sciper_id: str | None = None
    scopus_id: str | None = None
    email_hash: str | None = None
    primary_affiliation: str | None = None
    primary_affiliation_uuid: str | None = None
    affiliation_uuids: list[str] = Field(default_factory=list)
    position: str | None = None
    biography: str | None = None
    research_interests: list[str] = Field(default_factory=list)
    profile_url: str | None = None
    related_article_uuids: list[str] = Field(default_factory=list)


class OrganizationRecord(BaseModel):
    """One row of `ethz_research_collection_organizations`."""

    org_uuid: str
    name: str | None = None
    acronym: str | None = None
    aliases: list[str] = Field(default_factory=list)
    parent_org_uuid: str | None = None
    parent_org_chain: list[str] = Field(default_factory=list)
    parent_org_chain_names: list[str] = Field(default_factory=list)
    description: str | None = None
    sciper_unit_id: str | None = None
    ror_id: str | None = None
    unit_manager_uuid: str | None = None
    unit_manager_name: str | None = None
    research_collection_url: str | None = None
    related_article_uuids: list[str] = Field(default_factory=list)
