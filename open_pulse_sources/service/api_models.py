"""Pydantic contracts for the index service API.

Extracted from git-metadata-extractor src/v2/api_models/contracts.py
(the index-related subset, byte-identical models).
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# Upper bound on per-request ingest batch size — caps resource use on the
# (token-gated) /v2/indices/*/ingest endpoints (audit: ingest-list-no-maxlen).
_MAX_INGEST_BATCH = 1000
# Upper bound on a free-text search query (audit: search-query-unbounded-string).
_MAX_QUERY_CHARS = 4000

class IndexIngestJobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class ZenodoIngestRequest(BaseModel):
    """Body for `POST /v2/indices/zenodo/ingest`."""

    model_config = ConfigDict(extra="forbid")

    ids: list[str] = Field(
        min_length=1,
        max_length=_MAX_INGEST_BATCH,
        description=(
            "One or more Zenodo record identifiers. Bare numeric ids, "
            "DOIs (`10.5281/zenodo.…`), or full Zenodo URLs are accepted."
        ),
    )
    refresh: bool = Field(
        default=False,
        description="If true, re-fetch records already present in the local store.",
    )


class GitHubIngestRequest(BaseModel):
    """Body for `POST /v2/indices/github/ingest`."""

    model_config = ConfigDict(extra="forbid")

    repos: list[str] = Field(
        min_length=1,
        max_length=_MAX_INGEST_BATCH,
        description="One or more GitHub repo handles in the form `owner/name`.",
    )


class GitHubUsersIngestRequest(BaseModel):
    """Body for `POST /v2/indices/github_users/ingest`."""

    model_config = ConfigDict(extra="forbid")

    logins: list[str] = Field(
        min_length=1,
        max_length=_MAX_INGEST_BATCH,
        description="One or more GitHub user logins (bare handles, not URLs).",
    )


class GitHubOrgsIngestRequest(BaseModel):
    """Body for `POST /v2/indices/github_organizations/ingest`."""

    model_config = ConfigDict(extra="forbid")

    orgs: list[str] = Field(
        min_length=1,
        max_length=_MAX_INGEST_BATCH,
        description="One or more GitHub organization handles (bare, not URLs).",
    )


class HuggingFacePapersIngestRequest(BaseModel):
    """Body for `POST /v2/indices/huggingface_papers/ingest`."""

    model_config = ConfigDict(extra="forbid")

    arxiv_ids: list[str] = Field(
        min_length=1,
        max_length=_MAX_INGEST_BATCH,
        description=(
            "One or more arXiv identifiers. Accepts any wire shape: bare id "
            "(`2310.01234`), versioned (`2310.01234v2`), arXiv URL "
            "(`https://arxiv.org/abs/...`), HF Papers URL "
            "(`https://huggingface.co/papers/...`), `arxiv:<id>` tag, or "
            "arXiv DOI (`10.48550/arXiv.<id>` / `https://doi.org/...`)."
        ),
    )


class HuggingFaceModelsIngestRequest(BaseModel):
    """Body for `POST /v2/indices/huggingface_models/ingest`."""

    model_config = ConfigDict(extra="forbid")

    repo_ids: list[str] = Field(
        min_length=1,
        max_length=_MAX_INGEST_BATCH,
        description="One or more HF model repo_ids in the form `namespace/name`.",
    )


class HuggingFaceDatasetsIngestRequest(BaseModel):
    """Body for `POST /v2/indices/huggingface_datasets/ingest`."""

    model_config = ConfigDict(extra="forbid")

    repo_ids: list[str] = Field(
        min_length=1,
        max_length=_MAX_INGEST_BATCH,
        description="One or more HF dataset repo_ids in the form `namespace/name`.",
    )


class HuggingFaceSpacesIngestRequest(BaseModel):
    """Body for `POST /v2/indices/huggingface_spaces/ingest`."""

    model_config = ConfigDict(extra="forbid")

    repo_ids: list[str] = Field(
        min_length=1,
        max_length=_MAX_INGEST_BATCH,
        description="One or more HF space repo_ids in the form `namespace/name`.",
    )


class HuggingFaceUsersIngestRequest(BaseModel):
    """Body for `POST /v2/indices/huggingface_users/ingest`."""

    model_config = ConfigDict(extra="forbid")

    slugs: list[str] = Field(
        min_length=1,
        max_length=_MAX_INGEST_BATCH,
        description="One or more HF user namespace slugs (bare handles).",
    )


class HuggingFaceOrganizationsIngestRequest(BaseModel):
    """Body for `POST /v2/indices/huggingface_organizations/ingest`."""

    model_config = ConfigDict(extra="forbid")

    slugs: list[str] = Field(
        min_length=1,
        max_length=_MAX_INGEST_BATCH,
        description="One or more HF organization namespace slugs (bare handles).",
    )


class OpenAlexIngestRequest(BaseModel):
    """Body for `POST /v2/indices/openalex/ingest`.

    Accepts OpenAlex work identifiers in any of the canonical forms: a short
    ``W…`` id, an ``https://openalex.org/W…`` URL, or a DOI (`10.…`).
    """

    model_config = ConfigDict(extra="forbid")

    ids: list[str] = Field(
        min_length=1,
        max_length=_MAX_INGEST_BATCH,
        description="One or more OpenAlex work IDs (`W…`), URLs, or DOIs.",
    )


class OrcidIngestRequest(BaseModel):
    """Body for `POST /v2/indices/orcid/ingest`."""

    model_config = ConfigDict(extra="forbid")

    orcid_ids: list[str] = Field(
        min_length=1,
        max_length=_MAX_INGEST_BATCH,
        description="One or more ORCID identifiers (`XXXX-XXXX-XXXX-XXXX`).",
    )


class RenkulabIngestRequest(BaseModel):
    """Body for `POST /v2/indices/renkulab/ingest`.

    Currently scoped to v2 project records; additional entity types can be
    added later without breaking the contract.
    """

    model_config = ConfigDict(extra="forbid")

    project_ids: list[str] = Field(
        min_length=1,
        max_length=_MAX_INGEST_BATCH,
        description="One or more Renku v2 project ids (slug or UUID).",
    )


class GitLabIngestRequest(BaseModel):
    """Body for `POST /v2/indices/gitlab_*/ingest`.

    Full public-instance crawl; ``limit`` optionally caps how many records are
    ingested (smoke tests / first run).
    """

    model_config = ConfigDict(extra="forbid")

    limit: int | None = Field(
        default=None,
        ge=1,
        le=1_000_000,
        description=(
            "Optional cap on records ingested this run; "
            "omit to crawl the whole instance."
        ),
    )


class SwissubaseIngestRequest(BaseModel):
    """Body for `POST /v2/indices/swissubase/ingest`."""

    model_config = ConfigDict(extra="forbid")

    study_ids: list[str] = Field(
        min_length=1,
        max_length=_MAX_INGEST_BATCH,
        description="One or more SWISSUbase numeric study ids.",
    )


class EthzResearchCollectionIngestRequest(BaseModel):
    """Body for `POST /v2/indices/ethz_research_collection/ingest`."""

    model_config = ConfigDict(extra="forbid")

    uuids: list[str] = Field(
        min_length=1,
        max_length=_MAX_INGEST_BATCH,
        description=(
            "One or more ETH Research Collection item UUIDs "
            "(DSpace `/core/items/{uuid}`)."
        ),
    )


class OamonitorIngestItem(BaseModel):
    """One Open Access Monitor (OAM-CH) document to ingest."""

    model_config = ConfigDict(extra="forbid")

    entity: Literal[
        "journals", "publications", "publishers", "organisations",
    ] = Field(
        description="OAM-CH collection the id belongs to.",
    )
    id: str = Field(
        min_length=1,
        description=(
            "Upstream `_id` of the document (string ids for journals/publishers, "
            "OpenAlex URLs for publications, ROR URLs for organisations)."
        ),
    )


class OamonitorIngestRequest(BaseModel):
    """Body for `POST /v2/indices/oamonitor/ingest`."""

    model_config = ConfigDict(extra="forbid")

    items: list[OamonitorIngestItem] = Field(
        min_length=1,
        max_length=_MAX_INGEST_BATCH,
        description="One or more {entity, id} pairs to ingest from OAM-CH.",
    )


class DockerhubIngestRequest(BaseModel):
    """Body for `POST /v2/indices/dockerhub/ingest`."""

    model_config = ConfigDict(extra="forbid")

    images: list[str] = Field(
        min_length=1,
        max_length=_MAX_INGEST_BATCH,
        description=(
            "One or more Docker Hub image references. Accepts `namespace/name`, "
            "a bare official-image name (`python` -> `library/python`), a "
            "`https://hub.docker.com/r/<ns>/<name>` or `/_/<name>` URL, or a "
            "`docker.io/...` pull reference (any `:tag` is dropped — repositories "
            "are the indexed unit)."
        ),
    )


class IndexSearchRequest(BaseModel):
    """Body for `POST /v2/indices/<name>/search`.

    Uniform across indices. Indices with a single entity type ignore
    ``target``; multi-entity indices use it to select the collection.
    ETHZ Research Collection accepts the ChromaDB-style ``filter_payload``
    as its ``where`` clause and falls back to ``mode="hybrid"``.
    """

    model_config = ConfigDict(extra="forbid")

    query: str = Field(
        min_length=1,
        max_length=_MAX_QUERY_CHARS,
        description="Free-text query to match against the index.",
    )
    top_k: int = Field(
        default=10, ge=1, le=200,
        description="Maximum number of results to return.",
    )
    candidate_k: int | None = Field(
        default=None, ge=1, le=1000,
        description="Vector-search candidate count before reranking. Indices that do not rerank ignore this.",
    )
    filter_payload: dict[str, Any] | None = Field(
        default=None,
        description="Optional metadata filter dict. Shape is index-specific (Qdrant for most, ChromaDB-style `where` for ETHZ Research Collection).",
    )
    target: str | None = Field(
        default=None,
        description="Optional entity type / collection target for multi-entity indices (e.g. huggingface: model|dataset|space|org; openalex: works|authors|institutions|sources|topics|concepts; ethz_research_collection: chunks|articles|persons|organizations).",
    )


class IndexSearchHit(BaseModel):
    """One result row returned by an index search."""

    model_config = ConfigDict(extra="allow")

    id: str
    vector_score: float | None = None
    rerank_score: float | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    entity: dict[str, Any] | None = None


class IndexSearchResponse(BaseModel):
    """Wrapper envelope for index search results."""

    index_name: IndexName
    target: str | None = None
    query: str
    hits: list[IndexSearchHit] = Field(default_factory=list)
    extra: dict[str, Any] | None = Field(
        default=None,
        description="Index-specific extras (e.g. ETHZ Research Collection related persons/orgs, HuggingFace facets). Optional.",
    )


IndexName = Literal[
    "zenodo_records",
    "huggingface_papers",
    "huggingface_models",
    "huggingface_datasets",
    "huggingface_spaces",
    "huggingface_users",
    "huggingface_organizations",
    "github_repos",
    "github_users",
    "github_organizations",
    "openalex",
    "orcid",
    "renkulab",
    "swissubase",
    "ethz_research_collection",
    "oamonitor",
    "dockerhub",
    # CLI-managed catalogs — search routes added in the stats/search
    # coverage extension PR. No v2 ingest route (ingest happens via
    # `python -m open_pulse_sources.index.<name> ingest`).
    "ror",
    "infoscience",
    "snsf",
    "epfl_graph",
    "zenodo_communities",
    # GitLab index family — full ingest + semantic search routes.
    "gitlab_epfl_projects",
    "gitlab_epfl_groups",
    "gitlab_epfl_users",
    "gitlab_ethz_projects",
    "gitlab_ethz_groups",
    "gitlab_ethz_users",
    "gitlab_datascience_projects",
    "gitlab_datascience_groups",
    "gitlab_datascience_users",
]


class IndexIngestJob(BaseModel):
    """Persistent record for an async index-ingest job."""

    job_id: str
    index_name: IndexName
    status: IndexIngestJobStatus
    request: dict[str, Any]
    submitted_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    summary: dict[str, Any] | None = None
    error: str | None = None


class IndexIngestJobAccepted(BaseModel):
    """Response body for the POST that enqueues an ingest job."""

    job_id: str
    index_name: IndexName
    status: IndexIngestJobStatus
    status_url: str
    submitted_at: datetime
