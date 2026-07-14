"""Index management API — ingest / search / stats / compact / reset routes.

Extracted verbatim from git-metadata-extractor's ``src/v2/api.py`` (the
``/v2/manifest`` + ``/v2/indices/*`` block). Routes keep the ``/v2`` prefix
so existing consumers can point at this service without client changes.
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Annotated, Any
from uuid import uuid4

from fastapi import APIRouter, Depends, Path, Query, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from open_pulse_sources.common.cache import ProviderCache
from open_pulse_sources.service.api_models import (
    DockerhubIngestRequest,
    EthzResearchCollectionIngestRequest,
    GitHubIngestRequest,
    GitHubOrgsIngestRequest,
    GitHubUsersIngestRequest,
    GitLabIngestRequest,
    HuggingFaceDatasetsIngestRequest,
    HuggingFaceModelsIngestRequest,
    HuggingFaceOrganizationsIngestRequest,
    HuggingFacePapersIngestRequest,
    HuggingFaceSpacesIngestRequest,
    HuggingFaceUsersIngestRequest,
    IndexIngestJob,
    IndexIngestJobAccepted,
    IndexIngestJobStatus,
    IndexSearchRequest,
    IndexSearchResponse,
    OamonitorIngestRequest,
    OpenAlexIngestRequest,
    OrcidIngestRequest,
    RenkulabIngestRequest,
    SwissubaseIngestRequest,
    ZenodoIngestRequest,
)
from open_pulse_sources.service.auth import verify_token
from open_pulse_sources.service.indices.cli_catalogs import (
    run_communities_search,
    run_epfl_graph_search,
    run_infoscience_search,
    run_ror_search,
    run_snsf_search,
)
from open_pulse_sources.service.indices.compact import (
    CompactResult,
    close_cached_resources_for,
    compact_duckdb,
)
from open_pulse_sources.service.indices.dockerhub import (
    run_dockerhub_ingest_job,
    run_dockerhub_search,
)
from open_pulse_sources.service.indices.ethz_research_collection import (
    run_ethz_research_collection_ingest_job,
    run_ethz_research_collection_search,
)
from open_pulse_sources.service.indices.github_organizations import (
    run_github_orgs_ingest_job,
    run_github_orgs_search,
)
from open_pulse_sources.service.indices.github_repos import (
    run_github_repos_ingest_job,
    run_github_repos_search,
)
from open_pulse_sources.service.indices.github_users import (
    run_github_users_ingest_job,
    run_github_users_search,
)
from open_pulse_sources.service.indices.gitlab import (
    GITLAB_INDEX_NAMES,
    run_gitlab_ingest_job,
    run_gitlab_search,
)
from open_pulse_sources.service.indices.huggingface_datasets import (
    run_huggingface_datasets_ingest_job,
    run_huggingface_datasets_search,
)
from open_pulse_sources.service.indices.huggingface_models import (
    run_huggingface_models_ingest_job,
    run_huggingface_models_search,
)
from open_pulse_sources.service.indices.huggingface_organizations import (
    run_huggingface_organizations_ingest_job,
    run_huggingface_organizations_search,
)
from open_pulse_sources.service.indices.huggingface_papers import (
    run_huggingface_papers_ingest_job,
    run_huggingface_papers_search,
)
from open_pulse_sources.service.indices.huggingface_spaces import (
    run_huggingface_spaces_ingest_job,
    run_huggingface_spaces_search,
)
from open_pulse_sources.service.indices.huggingface_users import (
    run_huggingface_users_ingest_job,
    run_huggingface_users_search,
)
from open_pulse_sources.service.indices.jobs import IndexIngestJobStore
from open_pulse_sources.service.indices.oamonitor import (
    run_oamonitor_ingest_job,
    run_oamonitor_search,
)
from open_pulse_sources.service.indices.openalex import run_openalex_ingest_job, run_openalex_search
from open_pulse_sources.service.indices.orcid import run_orcid_ingest_job, run_orcid_search
from open_pulse_sources.service.indices.renkulab import run_renkulab_ingest_job, run_renkulab_search
from open_pulse_sources.service.indices.stats import (
    INDEX_STATS_SUPPORTED_PROVIDERS,
    IndexStatsResponse,
    UnknownIndexProviderError,
    collect_index_stats,
    fetch_store_for_stats,
)
from open_pulse_sources.service.indices.swissubase import (
    run_swissubase_ingest_job,
    run_swissubase_search,
)
from open_pulse_sources.service.indices.zenodo_records import (
    run_zenodo_records_ingest_job,
    run_zenodo_records_search,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v2")

SECONDS_PER_DAY = 86_400
_FALSEY_ENV = {"false", "0", "no", "off"}


def _resolve_provider_cache(app_state: Any) -> ProviderCache | None:
    """Reuse the app-level ProviderCache, creating it on first use.

    Mirrors the monolith's ``src/v2/dependencies._resolve_provider_cache``;
    env knobs (``V2_PROVIDER_CACHE_*``) keep their names so an existing
    deployment can point at this service without config changes.
    """
    existing = getattr(app_state, "v2_provider_cache", None)
    if isinstance(existing, ProviderCache):
        return existing
    enabled = os.getenv("V2_PROVIDER_CACHE_ENABLED", "true").strip().lower()
    if enabled in _FALSEY_ENV:
        return None
    cache = ProviderCache(
        os.getenv("V2_PROVIDER_CACHE_PATH", ".cache/v2/providers.db"),
        default_ttl_seconds=int(os.getenv("V2_PROVIDER_CACHE_TTL_DAYS", "30"))
        * SECONDS_PER_DAY,
    )
    app_state.v2_provider_cache = cache
    return cache


def _track_background_task(request: Request, task: asyncio.Task[Any]) -> None:
    """Hold a strong reference to a background task so it isn't GC'd mid-flight."""
    tasks: set[asyncio.Task[Any]] | None = getattr(
        request.app.state,
        "_v2_job_tasks",
        None,
    )
    if tasks is None:
        tasks = set()
        request.app.state._v2_job_tasks = tasks  # noqa: SLF001
    tasks.add(task)
    task.add_done_callback(tasks.discard)

# --- /v2/indices/<name>/ingest --------------------------------------------
# Async ingestion routes for the RAG indices. Each POST enqueues a job in the
# shared `IndexIngestJobStore` and dispatches the heavy work to a background
# task; clients poll `GET /v2/indices/jobs/{job_id}` for the outcome.


def _resolve_index_ingest_job_store(request: Request) -> IndexIngestJobStore | None:
    cache = _resolve_provider_cache(request.app.state)
    if not isinstance(cache, ProviderCache):
        return None
    return IndexIngestJobStore(cache)


def _index_job_status_path(job_id: str) -> str:
    return f"/v2/indices/jobs/{job_id}"


@router.get(
    "/manifest",
    tags=["Indices"],
)
async def get_manifest(
    _token: Annotated[str, Depends(verify_token)],
    sources: Annotated[
        bool,
        Query(description="Only stores that should appear as Hub 'Sources' tiles."),
    ] = False,
) -> list[dict[str, Any]]:
    """Federated index-store manifest — the contract consumers build against.

    One entry per registered store:
    ``{name, duckdb, entity_types, backend, surface_as_source, id_shape}``.
    Mirrors ``python -m open_pulse_sources.index._federated.manifest``. ``?sources=true``
    returns only the stores that should surface as Hub "Sources" tiles
    (vector-backed plus allowlisted DuckDB-only).
    """
    from open_pulse_sources.index._federated.manifest import build_manifest  # noqa: PLC0415

    return build_manifest(sources_only=sources)


@router.post(
    "/indices/zenodo_records/ingest",
    response_model=IndexIngestJobAccepted,
    response_model_exclude_none=True,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["Indices"],
)
async def zenodo_ingest_post(
    payload: ZenodoIngestRequest,
    request: Request,
    _token: Annotated[str, Depends(verify_token)],
) -> IndexIngestJobAccepted | JSONResponse:
    """Enqueue a Zenodo ingest for one or more record ids."""

    job_store = _resolve_index_ingest_job_store(request)
    if job_store is None:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "detail": "index ingest job store unavailable: provider cache is disabled",
            },
        )

    job_id = str(uuid4())
    submitted_at = datetime.now(timezone.utc)
    job = IndexIngestJob(
        job_id=job_id,
        index_name="zenodo_records",
        status=IndexIngestJobStatus.PENDING,
        request=payload.model_dump(mode="json"),
        submitted_at=submitted_at,
    )
    job_store.set(job)

    task = asyncio.create_task(
        run_zenodo_records_ingest_job(
            payload=payload,
            app_state=request.app.state,
            job_store=job_store,
            job_id=job_id,
        ),
    )
    _track_background_task(request, task)

    logger.info(
        "zenodo ingest job submitted: job_id=%s ids=%d refresh=%s",
        job_id,
        len(payload.ids),
        payload.refresh,
    )
    return IndexIngestJobAccepted(
        job_id=job_id,
        index_name="zenodo_records",
        status=IndexIngestJobStatus.PENDING,
        status_url=_index_job_status_path(job_id),
        submitted_at=submitted_at,
    )


def _hf_entity_ingest_post(
    request: Request,
    *,
    index_name: str,
    payload: Any,
    runner: Any,
    item_count: int,
) -> IndexIngestJobAccepted | JSONResponse:
    """Shared body for the five per-entity HF ingest endpoints. Each
    POST handler delegates here after pulling its typed payload + the
    matching `run_*_ingest_job` coroutine."""
    job_store = _resolve_index_ingest_job_store(request)
    if job_store is None:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "detail": "index ingest job store unavailable: provider cache is disabled",
            },
        )
    job_id = str(uuid4())
    submitted_at = datetime.now(timezone.utc)
    job = IndexIngestJob(
        job_id=job_id,
        index_name=index_name,
        status=IndexIngestJobStatus.PENDING,
        request=payload.model_dump(mode="json"),
        submitted_at=submitted_at,
    )
    job_store.set(job)
    task = asyncio.create_task(
        runner(
            payload=payload,
            app_state=request.app.state,
            job_store=job_store,
            job_id=job_id,
        ),
    )
    _track_background_task(request, task)
    logger.info(
        "%s ingest job submitted: job_id=%s items=%d",
        index_name, job_id, item_count,
    )
    return IndexIngestJobAccepted(
        job_id=job_id,
        index_name=index_name,
        status=IndexIngestJobStatus.PENDING,
        status_url=_index_job_status_path(job_id),
        submitted_at=submitted_at,
    )


@router.post(
    "/indices/huggingface_models/ingest",
    response_model=IndexIngestJobAccepted,
    response_model_exclude_none=True,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["Indices"],
)
async def huggingface_models_ingest_post(
    payload: HuggingFaceModelsIngestRequest,
    request: Request,
    _token: Annotated[str, Depends(verify_token)],
) -> IndexIngestJobAccepted | JSONResponse:
    """Enqueue a HuggingFace models ingest for one or more repo_ids."""
    return _hf_entity_ingest_post(
        request,
        index_name="huggingface_models",
        payload=payload,
        runner=run_huggingface_models_ingest_job,
        item_count=len(payload.repo_ids),
    )


@router.post(
    "/indices/huggingface_datasets/ingest",
    response_model=IndexIngestJobAccepted,
    response_model_exclude_none=True,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["Indices"],
)
async def huggingface_datasets_ingest_post(
    payload: HuggingFaceDatasetsIngestRequest,
    request: Request,
    _token: Annotated[str, Depends(verify_token)],
) -> IndexIngestJobAccepted | JSONResponse:
    """Enqueue a HuggingFace datasets ingest for one or more repo_ids."""
    return _hf_entity_ingest_post(
        request,
        index_name="huggingface_datasets",
        payload=payload,
        runner=run_huggingface_datasets_ingest_job,
        item_count=len(payload.repo_ids),
    )


@router.post(
    "/indices/huggingface_spaces/ingest",
    response_model=IndexIngestJobAccepted,
    response_model_exclude_none=True,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["Indices"],
)
async def huggingface_spaces_ingest_post(
    payload: HuggingFaceSpacesIngestRequest,
    request: Request,
    _token: Annotated[str, Depends(verify_token)],
) -> IndexIngestJobAccepted | JSONResponse:
    """Enqueue a HuggingFace spaces ingest for one or more repo_ids."""
    return _hf_entity_ingest_post(
        request,
        index_name="huggingface_spaces",
        payload=payload,
        runner=run_huggingface_spaces_ingest_job,
        item_count=len(payload.repo_ids),
    )


@router.post(
    "/indices/huggingface_users/ingest",
    response_model=IndexIngestJobAccepted,
    response_model_exclude_none=True,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["Indices"],
)
async def huggingface_users_ingest_post(
    payload: HuggingFaceUsersIngestRequest,
    request: Request,
    _token: Annotated[str, Depends(verify_token)],
) -> IndexIngestJobAccepted | JSONResponse:
    """Enqueue a HuggingFace users ingest for one or more namespace slugs."""
    return _hf_entity_ingest_post(
        request,
        index_name="huggingface_users",
        payload=payload,
        runner=run_huggingface_users_ingest_job,
        item_count=len(payload.slugs),
    )


@router.post(
    "/indices/huggingface_organizations/ingest",
    response_model=IndexIngestJobAccepted,
    response_model_exclude_none=True,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["Indices"],
)
async def huggingface_organizations_ingest_post(
    payload: HuggingFaceOrganizationsIngestRequest,
    request: Request,
    _token: Annotated[str, Depends(verify_token)],
) -> IndexIngestJobAccepted | JSONResponse:
    """Enqueue a HuggingFace organizations ingest for one or more namespace slugs."""
    return _hf_entity_ingest_post(
        request,
        index_name="huggingface_organizations",
        payload=payload,
        runner=run_huggingface_organizations_ingest_job,
        item_count=len(payload.slugs),
    )


@router.post(
    "/indices/github_repos/ingest",
    response_model=IndexIngestJobAccepted,
    response_model_exclude_none=True,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["Indices"],
)
async def github_ingest_post(
    payload: GitHubIngestRequest,
    request: Request,
    _token: Annotated[str, Depends(verify_token)],
) -> IndexIngestJobAccepted | JSONResponse:
    """Enqueue a GitHub ingest for one or more `owner/name` repo handles."""

    job_store = _resolve_index_ingest_job_store(request)
    if job_store is None:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "detail": "index ingest job store unavailable: provider cache is disabled",
            },
        )
    job_id = str(uuid4())
    submitted_at = datetime.now(timezone.utc)
    job = IndexIngestJob(
        job_id=job_id, index_name="github_repos", status=IndexIngestJobStatus.PENDING,
        request=payload.model_dump(mode="json"), submitted_at=submitted_at,
    )
    job_store.set(job)
    task = asyncio.create_task(
        run_github_repos_ingest_job(
            payload=payload, app_state=request.app.state,
            job_store=job_store, job_id=job_id,
        ),
    )
    _track_background_task(request, task)
    logger.info("github ingest job submitted: job_id=%s repos=%d", job_id, len(payload.repos))
    return IndexIngestJobAccepted(
        job_id=job_id, index_name="github_repos", status=IndexIngestJobStatus.PENDING,
        status_url=_index_job_status_path(job_id), submitted_at=submitted_at,
    )


@router.post(
    "/indices/github_users/ingest",
    response_model=IndexIngestJobAccepted,
    response_model_exclude_none=True,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["Indices"],
)
async def github_users_ingest_post(
    payload: GitHubUsersIngestRequest,
    request: Request,
    _token: Annotated[str, Depends(verify_token)],
) -> IndexIngestJobAccepted | JSONResponse:
    """Enqueue a github_users ingest for one or more user logins.

    Each login is fetched via `GET /users/{login}` and persisted to the
    github_users DuckDB + Qdrant collection. Org-typed payloads are
    skipped (they belong in github_organizations).
    """
    job_store = _resolve_index_ingest_job_store(request)
    if job_store is None:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "detail": "index ingest job store unavailable: provider cache is disabled",
            },
        )
    job_id = str(uuid4())
    submitted_at = datetime.now(timezone.utc)
    job = IndexIngestJob(
        job_id=job_id, index_name="github_users", status=IndexIngestJobStatus.PENDING,
        request=payload.model_dump(mode="json"), submitted_at=submitted_at,
    )
    job_store.set(job)
    task = asyncio.create_task(
        run_github_users_ingest_job(
            payload=payload, app_state=request.app.state,
            job_store=job_store, job_id=job_id,
        ),
    )
    _track_background_task(request, task)
    logger.info(
        "github_users ingest job submitted: job_id=%s logins=%d",
        job_id, len(payload.logins),
    )
    return IndexIngestJobAccepted(
        job_id=job_id, index_name="github_users",
        status=IndexIngestJobStatus.PENDING,
        status_url=_index_job_status_path(job_id), submitted_at=submitted_at,
    )


@router.post(
    "/indices/github_organizations/ingest",
    response_model=IndexIngestJobAccepted,
    response_model_exclude_none=True,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["Indices"],
)
async def github_organizations_ingest_post(
    payload: GitHubOrgsIngestRequest,
    request: Request,
    _token: Annotated[str, Depends(verify_token)],
) -> IndexIngestJobAccepted | JSONResponse:
    """Enqueue a github_organizations ingest for one or more org handles.

    Each handle is fetched via `GET /orgs/{org}` and persisted to the
    github_organizations DuckDB + Qdrant collection.
    """
    job_store = _resolve_index_ingest_job_store(request)
    if job_store is None:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "detail": "index ingest job store unavailable: provider cache is disabled",
            },
        )
    job_id = str(uuid4())
    submitted_at = datetime.now(timezone.utc)
    job = IndexIngestJob(
        job_id=job_id, index_name="github_organizations",
        status=IndexIngestJobStatus.PENDING,
        request=payload.model_dump(mode="json"), submitted_at=submitted_at,
    )
    job_store.set(job)
    task = asyncio.create_task(
        run_github_orgs_ingest_job(
            payload=payload, app_state=request.app.state,
            job_store=job_store, job_id=job_id,
        ),
    )
    _track_background_task(request, task)
    logger.info(
        "github_organizations ingest job submitted: job_id=%s orgs=%d",
        job_id, len(payload.orgs),
    )
    return IndexIngestJobAccepted(
        job_id=job_id, index_name="github_organizations",
        status=IndexIngestJobStatus.PENDING,
        status_url=_index_job_status_path(job_id), submitted_at=submitted_at,
    )


@router.post(
    "/indices/huggingface_papers/ingest",
    response_model=IndexIngestJobAccepted,
    response_model_exclude_none=True,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["Indices"],
)
async def huggingface_papers_ingest_post(
    payload: HuggingFacePapersIngestRequest,
    request: Request,
    _token: Annotated[str, Depends(verify_token)],
) -> IndexIngestJobAccepted | JSONResponse:
    """Enqueue a huggingface_papers ingest for one or more arXiv ids.

    Each id can arrive in any wire shape — bare (`2310.01234`), with
    version suffix, as an arXiv or HF Papers URL, as an `arxiv:` tag,
    or as an arXiv DOI. The job normaliser strips to the canonical id
    before fetch.
    """
    job_store = _resolve_index_ingest_job_store(request)
    if job_store is None:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "detail": "index ingest job store unavailable: provider cache is disabled",
            },
        )
    job_id = str(uuid4())
    submitted_at = datetime.now(timezone.utc)
    job = IndexIngestJob(
        job_id=job_id, index_name="huggingface_papers",
        status=IndexIngestJobStatus.PENDING,
        request=payload.model_dump(mode="json"), submitted_at=submitted_at,
    )
    job_store.set(job)
    task = asyncio.create_task(
        run_huggingface_papers_ingest_job(
            payload=payload, app_state=request.app.state,
            job_store=job_store, job_id=job_id,
        ),
    )
    _track_background_task(request, task)
    logger.info(
        "huggingface_papers ingest job submitted: job_id=%s arxiv_ids=%d",
        job_id, len(payload.arxiv_ids),
    )
    return IndexIngestJobAccepted(
        job_id=job_id, index_name="huggingface_papers",
        status=IndexIngestJobStatus.PENDING,
        status_url=_index_job_status_path(job_id), submitted_at=submitted_at,
    )


@router.post(
    "/indices/openalex/ingest",
    response_model=IndexIngestJobAccepted,
    response_model_exclude_none=True,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["Indices"],
)
async def openalex_ingest_post(
    payload: OpenAlexIngestRequest,
    request: Request,
    _token: Annotated[str, Depends(verify_token)],
) -> IndexIngestJobAccepted | JSONResponse:
    """Enqueue an OpenAlex ingest for one or more work IDs / URLs / DOIs."""

    job_store = _resolve_index_ingest_job_store(request)
    if job_store is None:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "detail": "index ingest job store unavailable: provider cache is disabled",
            },
        )
    job_id = str(uuid4())
    submitted_at = datetime.now(timezone.utc)
    job = IndexIngestJob(
        job_id=job_id, index_name="openalex", status=IndexIngestJobStatus.PENDING,
        request=payload.model_dump(mode="json"), submitted_at=submitted_at,
    )
    job_store.set(job)
    task = asyncio.create_task(
        run_openalex_ingest_job(
            payload=payload, app_state=request.app.state,
            job_store=job_store, job_id=job_id,
        ),
    )
    _track_background_task(request, task)
    logger.info("openalex ingest job submitted: job_id=%s ids=%d", job_id, len(payload.ids))
    return IndexIngestJobAccepted(
        job_id=job_id, index_name="openalex", status=IndexIngestJobStatus.PENDING,
        status_url=_index_job_status_path(job_id), submitted_at=submitted_at,
    )


@router.post(
    "/indices/orcid/ingest",
    response_model=IndexIngestJobAccepted,
    response_model_exclude_none=True,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["Indices"],
)
async def orcid_ingest_post(
    payload: OrcidIngestRequest,
    request: Request,
    _token: Annotated[str, Depends(verify_token)],
) -> IndexIngestJobAccepted | JSONResponse:
    """Enqueue an ORCID ingest for one or more ORCID identifiers."""

    job_store = _resolve_index_ingest_job_store(request)
    if job_store is None:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "detail": "index ingest job store unavailable: provider cache is disabled",
            },
        )
    job_id = str(uuid4())
    submitted_at = datetime.now(timezone.utc)
    job = IndexIngestJob(
        job_id=job_id, index_name="orcid", status=IndexIngestJobStatus.PENDING,
        request=payload.model_dump(mode="json"), submitted_at=submitted_at,
    )
    job_store.set(job)
    task = asyncio.create_task(
        run_orcid_ingest_job(
            payload=payload, app_state=request.app.state,
            job_store=job_store, job_id=job_id,
        ),
    )
    _track_background_task(request, task)
    logger.info("orcid ingest job submitted: job_id=%s ids=%d", job_id, len(payload.orcid_ids))
    return IndexIngestJobAccepted(
        job_id=job_id, index_name="orcid", status=IndexIngestJobStatus.PENDING,
        status_url=_index_job_status_path(job_id), submitted_at=submitted_at,
    )


@router.post(
    "/indices/renkulab/ingest",
    response_model=IndexIngestJobAccepted,
    response_model_exclude_none=True,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["Indices"],
)
async def renkulab_ingest_post(
    payload: RenkulabIngestRequest,
    request: Request,
    _token: Annotated[str, Depends(verify_token)],
) -> IndexIngestJobAccepted | JSONResponse:
    """Enqueue a Renkulab ingest for one or more project ids (UUID or namespace/slug)."""

    job_store = _resolve_index_ingest_job_store(request)
    if job_store is None:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "detail": "index ingest job store unavailable: provider cache is disabled",
            },
        )
    job_id = str(uuid4())
    submitted_at = datetime.now(timezone.utc)
    job = IndexIngestJob(
        job_id=job_id, index_name="renkulab", status=IndexIngestJobStatus.PENDING,
        request=payload.model_dump(mode="json"), submitted_at=submitted_at,
    )
    job_store.set(job)
    task = asyncio.create_task(
        run_renkulab_ingest_job(
            payload=payload, app_state=request.app.state,
            job_store=job_store, job_id=job_id,
        ),
    )
    _track_background_task(request, task)
    logger.info(
        "renkulab ingest job submitted: job_id=%s project_ids=%d",
        job_id, len(payload.project_ids),
    )
    return IndexIngestJobAccepted(
        job_id=job_id, index_name="renkulab", status=IndexIngestJobStatus.PENDING,
        status_url=_index_job_status_path(job_id), submitted_at=submitted_at,
    )


@router.post(
    "/indices/swissubase/ingest",
    response_model=IndexIngestJobAccepted,
    response_model_exclude_none=True,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["Indices"],
)
async def swissubase_ingest_post(
    payload: SwissubaseIngestRequest,
    request: Request,
    _token: Annotated[str, Depends(verify_token)],
) -> IndexIngestJobAccepted | JSONResponse:
    """Enqueue a SWISSUbase ingest for one or more numeric study ids."""

    job_store = _resolve_index_ingest_job_store(request)
    if job_store is None:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "detail": "index ingest job store unavailable: provider cache is disabled",
            },
        )
    job_id = str(uuid4())
    submitted_at = datetime.now(timezone.utc)
    job = IndexIngestJob(
        job_id=job_id, index_name="swissubase", status=IndexIngestJobStatus.PENDING,
        request=payload.model_dump(mode="json"), submitted_at=submitted_at,
    )
    job_store.set(job)
    task = asyncio.create_task(
        run_swissubase_ingest_job(
            payload=payload, app_state=request.app.state,
            job_store=job_store, job_id=job_id,
        ),
    )
    _track_background_task(request, task)
    logger.info(
        "swissubase ingest job submitted: job_id=%s study_ids=%d",
        job_id, len(payload.study_ids),
    )
    return IndexIngestJobAccepted(
        job_id=job_id, index_name="swissubase", status=IndexIngestJobStatus.PENDING,
        status_url=_index_job_status_path(job_id), submitted_at=submitted_at,
    )


@router.post(
    "/indices/ethz_research_collection/ingest",
    response_model=IndexIngestJobAccepted,
    response_model_exclude_none=True,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["Indices"],
)
async def ethz_research_collection_ingest_post(
    payload: EthzResearchCollectionIngestRequest,
    request: Request,
    _token: Annotated[str, Depends(verify_token)],
) -> IndexIngestJobAccepted | JSONResponse:
    """Enqueue an ETH Research Collection ingest for one or more item UUIDs."""

    job_store = _resolve_index_ingest_job_store(request)
    if job_store is None:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "detail": "index ingest job store unavailable: provider cache is disabled",
            },
        )
    job_id = str(uuid4())
    submitted_at = datetime.now(timezone.utc)
    job = IndexIngestJob(
        job_id=job_id, index_name="ethz_research_collection",
        status=IndexIngestJobStatus.PENDING,
        request=payload.model_dump(mode="json"), submitted_at=submitted_at,
    )
    job_store.set(job)
    task = asyncio.create_task(
        run_ethz_research_collection_ingest_job(
            payload=payload, app_state=request.app.state,
            job_store=job_store, job_id=job_id,
        ),
    )
    _track_background_task(request, task)
    logger.info(
        "ethz_research_collection ingest job submitted: job_id=%s uuids=%d",
        job_id, len(payload.uuids),
    )
    return IndexIngestJobAccepted(
        job_id=job_id, index_name="ethz_research_collection",
        status=IndexIngestJobStatus.PENDING,
        status_url=_index_job_status_path(job_id), submitted_at=submitted_at,
    )


@router.post(
    "/indices/oamonitor/ingest",
    response_model=IndexIngestJobAccepted,
    response_model_exclude_none=True,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["Indices"],
)
async def oamonitor_ingest_post(
    payload: OamonitorIngestRequest,
    request: Request,
    _token: Annotated[str, Depends(verify_token)],
) -> IndexIngestJobAccepted | JSONResponse:
    """Enqueue an OAM-CH ingest for one or more `{entity, id}` items."""

    job_store = _resolve_index_ingest_job_store(request)
    if job_store is None:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "detail": "index ingest job store unavailable: provider cache is disabled",
            },
        )
    job_id = str(uuid4())
    submitted_at = datetime.now(timezone.utc)
    job = IndexIngestJob(
        job_id=job_id, index_name="oamonitor",
        status=IndexIngestJobStatus.PENDING,
        request=payload.model_dump(mode="json"), submitted_at=submitted_at,
    )
    job_store.set(job)
    task = asyncio.create_task(
        run_oamonitor_ingest_job(
            payload=payload, app_state=request.app.state,
            job_store=job_store, job_id=job_id,
        ),
    )
    _track_background_task(request, task)
    logger.info(
        "oamonitor ingest job submitted: job_id=%s items=%d",
        job_id, len(payload.items),
    )
    return IndexIngestJobAccepted(
        job_id=job_id, index_name="oamonitor",
        status=IndexIngestJobStatus.PENDING,
        status_url=_index_job_status_path(job_id), submitted_at=submitted_at,
    )


@router.post(
    "/indices/dockerhub/ingest",
    response_model=IndexIngestJobAccepted,
    response_model_exclude_none=True,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["Indices"],
)
async def dockerhub_ingest_post(
    payload: DockerhubIngestRequest,
    request: Request,
    _token: Annotated[str, Depends(verify_token)],
) -> IndexIngestJobAccepted | JSONResponse:
    """Enqueue a Docker Hub ingest for one or more image references."""

    job_store = _resolve_index_ingest_job_store(request)
    if job_store is None:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "detail": "index ingest job store unavailable: provider cache is disabled",
            },
        )
    job_id = str(uuid4())
    submitted_at = datetime.now(timezone.utc)
    job = IndexIngestJob(
        job_id=job_id, index_name="dockerhub", status=IndexIngestJobStatus.PENDING,
        request=payload.model_dump(mode="json"), submitted_at=submitted_at,
    )
    job_store.set(job)
    task = asyncio.create_task(
        run_dockerhub_ingest_job(
            payload=payload, app_state=request.app.state,
            job_store=job_store, job_id=job_id,
        ),
    )
    _track_background_task(request, task)
    logger.info(
        "dockerhub ingest job submitted: job_id=%s images=%d",
        job_id, len(payload.images),
    )
    return IndexIngestJobAccepted(
        job_id=job_id, index_name="dockerhub", status=IndexIngestJobStatus.PENDING,
        status_url=_index_job_status_path(job_id), submitted_at=submitted_at,
    )


async def _search_response_or_unavailable(
    response: IndexSearchResponse | None, *, index_name: str,
) -> IndexSearchResponse | JSONResponse:
    if response is None:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "detail": f"{index_name} index module unavailable on this deployment",
            },
        )
    return response


@router.post(
    "/indices/zenodo_records/search",
    response_model=IndexSearchResponse,
    response_model_exclude_none=True,
    tags=["Indices"],
)
async def zenodo_search_post(
    payload: IndexSearchRequest,
    request: Request,
    _token: Annotated[str, Depends(verify_token)],
) -> IndexSearchResponse | JSONResponse:
    """Semantic search against the Zenodo index."""
    return await _search_response_or_unavailable(
        await run_zenodo_records_search(payload, request.app.state), index_name="zenodo_records",
    )


@router.post(
    "/indices/huggingface_models/search",
    response_model=IndexSearchResponse,
    response_model_exclude_none=True,
    tags=["Indices"],
)
async def huggingface_models_search_post(
    payload: IndexSearchRequest,
    request: Request,
    _token: Annotated[str, Depends(verify_token)],
) -> IndexSearchResponse | JSONResponse:
    """Semantic search against the huggingface_models index."""
    return await _search_response_or_unavailable(
        await run_huggingface_models_search(payload, request.app.state),
        index_name="huggingface_models",
    )


@router.post(
    "/indices/huggingface_datasets/search",
    response_model=IndexSearchResponse,
    response_model_exclude_none=True,
    tags=["Indices"],
)
async def huggingface_datasets_search_post(
    payload: IndexSearchRequest,
    request: Request,
    _token: Annotated[str, Depends(verify_token)],
) -> IndexSearchResponse | JSONResponse:
    """Semantic search against the huggingface_datasets index."""
    return await _search_response_or_unavailable(
        await run_huggingface_datasets_search(payload, request.app.state),
        index_name="huggingface_datasets",
    )


@router.post(
    "/indices/huggingface_spaces/search",
    response_model=IndexSearchResponse,
    response_model_exclude_none=True,
    tags=["Indices"],
)
async def huggingface_spaces_search_post(
    payload: IndexSearchRequest,
    request: Request,
    _token: Annotated[str, Depends(verify_token)],
) -> IndexSearchResponse | JSONResponse:
    """Semantic search against the huggingface_spaces index."""
    return await _search_response_or_unavailable(
        await run_huggingface_spaces_search(payload, request.app.state),
        index_name="huggingface_spaces",
    )


@router.post(
    "/indices/huggingface_users/search",
    response_model=IndexSearchResponse,
    response_model_exclude_none=True,
    tags=["Indices"],
)
async def huggingface_users_search_post(
    payload: IndexSearchRequest,
    request: Request,
    _token: Annotated[str, Depends(verify_token)],
) -> IndexSearchResponse | JSONResponse:
    """Semantic search against the huggingface_users index."""
    return await _search_response_or_unavailable(
        await run_huggingface_users_search(payload, request.app.state),
        index_name="huggingface_users",
    )


@router.post(
    "/indices/huggingface_organizations/search",
    response_model=IndexSearchResponse,
    response_model_exclude_none=True,
    tags=["Indices"],
)
async def huggingface_organizations_search_post(
    payload: IndexSearchRequest,
    request: Request,
    _token: Annotated[str, Depends(verify_token)],
) -> IndexSearchResponse | JSONResponse:
    """Semantic search against the huggingface_organizations index."""
    return await _search_response_or_unavailable(
        await run_huggingface_organizations_search(payload, request.app.state),
        index_name="huggingface_organizations",
    )


@router.post(
    "/indices/github_repos/search",
    response_model=IndexSearchResponse,
    response_model_exclude_none=True,
    tags=["Indices"],
)
async def github_search_post(
    payload: IndexSearchRequest,
    request: Request,
    _token: Annotated[str, Depends(verify_token)],
) -> IndexSearchResponse | JSONResponse:
    """Semantic search against the GitHub repos index."""
    return await _search_response_or_unavailable(
        await run_github_repos_search(payload, request.app.state), index_name="github_repos",
    )


@router.post(
    "/indices/github_users/search",
    response_model=IndexSearchResponse,
    response_model_exclude_none=True,
    tags=["Indices"],
)
async def github_users_search_post(
    payload: IndexSearchRequest,
    request: Request,
    _token: Annotated[str, Depends(verify_token)],
) -> IndexSearchResponse | JSONResponse:
    """Semantic search against the github_users index.

    Returns user cards ordered by relevance to the query — useful for
    disambiguating affiliations or finding a researcher by topic.
    """
    return await _search_response_or_unavailable(
        await run_github_users_search(payload, request.app.state),
        index_name="github_users",
    )


@router.post(
    "/indices/github_organizations/search",
    response_model=IndexSearchResponse,
    response_model_exclude_none=True,
    tags=["Indices"],
)
async def github_organizations_search_post(
    payload: IndexSearchRequest,
    request: Request,
    _token: Annotated[str, Depends(verify_token)],
) -> IndexSearchResponse | JSONResponse:
    """Semantic search against the github_organizations index."""
    return await _search_response_or_unavailable(
        await run_github_orgs_search(payload, request.app.state),
        index_name="github_organizations",
    )


@router.post(
    "/indices/huggingface_papers/search",
    response_model=IndexSearchResponse,
    response_model_exclude_none=True,
    tags=["Indices"],
)
async def huggingface_papers_search_post(
    payload: IndexSearchRequest,
    request: Request,
    _token: Annotated[str, Depends(verify_token)],
) -> IndexSearchResponse | JSONResponse:
    """Semantic search against the huggingface_papers index.

    Returns arXiv paper cards (HF-curated) ordered by relevance to
    the query. Useful for "find papers about X" queries grounded in
    the HF Papers daily feed and AI-summary metadata.
    """
    return await _search_response_or_unavailable(
        await run_huggingface_papers_search(payload, request.app.state),
        index_name="huggingface_papers",
    )


@router.post(
    "/indices/openalex/search",
    response_model=IndexSearchResponse,
    response_model_exclude_none=True,
    tags=["Indices"],
)
async def openalex_search_post(
    payload: IndexSearchRequest,
    request: Request,
    _token: Annotated[str, Depends(verify_token)],
) -> IndexSearchResponse | JSONResponse:
    """Semantic search against the OpenAlex index.

    Use ``target`` to pick the entity type: ``works`` (default), ``authors``,
    ``institutions``, ``sources``, ``topics``, ``concepts``.
    """
    return await _search_response_or_unavailable(
        await run_openalex_search(payload, request.app.state), index_name="openalex",
    )


@router.post(
    "/indices/orcid/search",
    response_model=IndexSearchResponse,
    response_model_exclude_none=True,
    tags=["Indices"],
)
async def orcid_search_post(
    payload: IndexSearchRequest,
    request: Request,
    _token: Annotated[str, Depends(verify_token)],
) -> IndexSearchResponse | JSONResponse:
    """Semantic search against the ORCID persons index."""
    return await _search_response_or_unavailable(
        await run_orcid_search(payload, request.app.state), index_name="orcid",
    )


@router.post(
    "/indices/renkulab/search",
    response_model=IndexSearchResponse,
    response_model_exclude_none=True,
    tags=["Indices"],
)
async def renkulab_search_post(
    payload: IndexSearchRequest,
    request: Request,
    _token: Annotated[str, Depends(verify_token)],
) -> IndexSearchResponse | JSONResponse:
    """Semantic search against the Renkulab index.

    ``target`` (optional) restricts the search to one of
    ``projects | datasets | users | groups | workflows``; omit to search
    across all configured entity types.
    """
    return await _search_response_or_unavailable(
        await run_renkulab_search(payload, request.app.state), index_name="renkulab",
    )


@router.post(
    "/indices/swissubase/search",
    response_model=IndexSearchResponse,
    response_model_exclude_none=True,
    tags=["Indices"],
)
async def swissubase_search_post(
    payload: IndexSearchRequest,
    request: Request,
    _token: Annotated[str, Depends(verify_token)],
) -> IndexSearchResponse | JSONResponse:
    """Semantic search against the SWISSUbase index."""
    return await _search_response_or_unavailable(
        await run_swissubase_search(payload, request.app.state),
        index_name="swissubase",
    )


@router.post(
    "/indices/ethz_research_collection/search",
    response_model=IndexSearchResponse,
    response_model_exclude_none=True,
    tags=["Indices"],
)
async def ethz_research_collection_search_post(
    payload: IndexSearchRequest,
    request: Request,
    _token: Annotated[str, Depends(verify_token)],
) -> IndexSearchResponse | JSONResponse:
    """Hybrid query against the ETH Research Collection index.

    ``target`` picks one of ``chunks`` (default), ``articles``, ``persons``,
    ``organizations``. ``filter_payload`` is forwarded as the ChromaDB-style
    ``where`` clause. Mode is fixed to ``hybrid``; for other modes use the
    standalone serve app directly.
    """
    return await _search_response_or_unavailable(
        await run_ethz_research_collection_search(payload, request.app.state),
        index_name="ethz_research_collection",
    )


@router.post(
    "/indices/oamonitor/search",
    response_model=IndexSearchResponse,
    response_model_exclude_none=True,
    tags=["Indices"],
)
async def oamonitor_search_post(
    payload: IndexSearchRequest,
    request: Request,
    _token: Annotated[str, Depends(verify_token)],
) -> IndexSearchResponse | JSONResponse:
    """Semantic search against the OAM-CH index.

    Use ``target`` to pick the entity collection: ``journals`` (default),
    ``publications``, ``publishers``, ``organisations``.
    """
    return await _search_response_or_unavailable(
        await run_oamonitor_search(payload, request.app.state),
        index_name="oamonitor",
    )


@router.post(
    "/indices/dockerhub/search",
    response_model=IndexSearchResponse,
    response_model_exclude_none=True,
    tags=["Indices"],
)
async def dockerhub_search_post(
    payload: IndexSearchRequest,
    request: Request,
    _token: Annotated[str, Depends(verify_token)],
) -> IndexSearchResponse | JSONResponse:
    """Semantic search against the Docker Hub index."""
    return await _search_response_or_unavailable(
        await run_dockerhub_search(payload, request.app.state),
        index_name="dockerhub",
    )


# --- /v2/indices/<name>/search for the CLI-managed catalogs ---------------
# These catalogs are populated by `python -m open_pulse_sources.index.<name>` from cron
# (no v2 ingest route) but have populated Qdrant collections. The thin
# shims in `open_pulse_sources.service.indices.cli_catalogs` translate `IndexSearchRequest`
# to each catalog's existing query function.


@router.post(
    "/indices/ror/search",
    response_model=IndexSearchResponse,
    response_model_exclude_none=True,
    tags=["Indices"],
)
async def ror_search_post(
    payload: IndexSearchRequest,
    request: Request,
    _token: Annotated[str, Depends(verify_token)],
) -> IndexSearchResponse | JSONResponse:
    """Semantic search against the ROR organisation index (125k+ orgs)."""
    return await _search_response_or_unavailable(
        await run_ror_search(payload, request.app.state),
        index_name="ror",
    )


@router.post(
    "/indices/infoscience/search",
    response_model=IndexSearchResponse,
    response_model_exclude_none=True,
    tags=["Indices"],
)
async def infoscience_search_post(
    payload: IndexSearchRequest,
    request: Request,
    _token: Annotated[str, Depends(verify_token)],
) -> IndexSearchResponse | JSONResponse:
    """Semantic search against the Infoscience publications index.

    Use ``target`` to pick the collection: ``chunks`` (default),
    ``articles``, ``persons``, ``organizations``.
    """
    return await _search_response_or_unavailable(
        await run_infoscience_search(payload, request.app.state),
        index_name="infoscience",
    )


@router.post(
    "/indices/snsf/search",
    response_model=IndexSearchResponse,
    response_model_exclude_none=True,
    tags=["Indices"],
)
async def snsf_search_post(
    payload: IndexSearchRequest,
    request: Request,
    _token: Annotated[str, Depends(verify_token)],
) -> IndexSearchResponse | JSONResponse:
    """Semantic search against the SNSF grants index."""
    return await _search_response_or_unavailable(
        await run_snsf_search(payload, request.app.state),
        index_name="snsf",
    )


@router.get(
    "/indices/snsf/grants",
    tags=["Indices"],
)
async def snsf_grants_get(  # noqa: PLR0913
    _token: Annotated[str, Depends(verify_token)],
    funding_instrument: Annotated[list[str] | None, Query(alias="scheme")] = None,
    research_institution: Annotated[list[str] | None, Query(alias="institution")] = None,
    state: Annotated[list[str] | None, Query(alias="status")] = None,
    main_discipline: Annotated[list[str] | None, Query(alias="discipline")] = None,
    main_field_of_research: Annotated[list[str] | None, Query(alias="field")] = None,
    call_decision_year: Annotated[list[int] | None, Query(alias="call_year")] = None,
    country: Annotated[list[str] | None, Query()] = None,
    person_number: Annotated[int | None, Query(alias="person")] = None,
    person_role: Annotated[str | None, Query(alias="role")] = None,
    has_output: Annotated[list[str] | None, Query()] = None,
    start_from: Annotated[str | None, Query()] = None,
    start_to: Annotated[str | None, Query()] = None,
    end_from: Annotated[str | None, Query()] = None,
    end_to: Annotated[str | None, Query()] = None,
    q: Annotated[str | None, Query()] = None,
    sort: Annotated[str, Query()] = "start_date_desc",
    limit: Annotated[int, Query()] = 50,
    offset: Annotated[int, Query()] = 0,
) -> dict[str, Any]:
    """Faceted SQL search over SNSF grants.

    Returns ``{"total": int, "results": [...]}`` where each result is a
    flat grant row.  All query parameters map 1-to-1 to ``GrantFilters``
    fields.  A missing or inaccessible store returns ``{"total":0,"results":[]}``.
    """
    try:
        from open_pulse_sources.index.snsf.facet_query import (  # noqa: PLC0415
            GrantFilters,
            query_grants,
        )
        from open_pulse_sources.index.snsf.storage.duckdb_store import SnsfStore  # noqa: PLC0415
    except Exception:  # noqa: BLE001
        return {"total": 0, "results": []}

    try:
        filters = GrantFilters(
            funding_instrument=funding_instrument,
            research_institution=research_institution,
            state=state,
            main_discipline=main_discipline,
            main_field_of_research=main_field_of_research,
            call_decision_year=call_decision_year,
            country=country,
            person_number=person_number,
            person_role=person_role,
            has_output=has_output,
            start_from=start_from,
            start_to=start_to,
            end_from=end_from,
            end_to=end_to,
        )
        store = SnsfStore.open()
        try:
            return query_grants(
                store, filters,
                text=q,
                sort=sort,
                limit=limit,
                offset=offset,
            )
        finally:
            store.close()
    except Exception:  # noqa: BLE001
        return {"total": 0, "results": []}


@router.get(
    "/indices/snsf/grants/facets",
    tags=["Indices"],
)
async def snsf_grants_facets_get(  # noqa: PLR0913
    _token: Annotated[str, Depends(verify_token)],
    funding_instrument: Annotated[list[str] | None, Query(alias="scheme")] = None,
    research_institution: Annotated[list[str] | None, Query(alias="institution")] = None,
    state: Annotated[list[str] | None, Query(alias="status")] = None,
    main_discipline: Annotated[list[str] | None, Query(alias="discipline")] = None,
    main_field_of_research: Annotated[list[str] | None, Query(alias="field")] = None,
    call_decision_year: Annotated[list[int] | None, Query(alias="call_year")] = None,
    country: Annotated[list[str] | None, Query()] = None,
    person_number: Annotated[int | None, Query(alias="person")] = None,
    person_role: Annotated[str | None, Query(alias="role")] = None,
    has_output: Annotated[list[str] | None, Query()] = None,
    start_from: Annotated[str | None, Query()] = None,
    start_to: Annotated[str | None, Query()] = None,
    end_from: Annotated[str | None, Query()] = None,
    end_to: Annotated[str | None, Query()] = None,
    q: Annotated[str | None, Query()] = None,
) -> dict[str, Any]:
    """Per-facet value→count with excluded-self semantics.

    Returns ``{facet_name: [{"value": ..., "count": ...}, ...], ...}``.
    A missing or inaccessible store returns ``{}``.
    """
    try:
        from open_pulse_sources.index.snsf.facet_query import (  # noqa: PLC0415
            GrantFilters,
            facet_counts,
        )
        from open_pulse_sources.index.snsf.storage.duckdb_store import SnsfStore  # noqa: PLC0415
    except Exception:  # noqa: BLE001
        return {}

    try:
        filters = GrantFilters(
            funding_instrument=funding_instrument,
            research_institution=research_institution,
            state=state,
            main_discipline=main_discipline,
            main_field_of_research=main_field_of_research,
            call_decision_year=call_decision_year,
            country=country,
            person_number=person_number,
            person_role=person_role,
            has_output=has_output,
            start_from=start_from,
            start_to=start_to,
            end_from=end_from,
            end_to=end_to,
        )
        store = SnsfStore.open()
        try:
            return facet_counts(store, filters, text=q)
        finally:
            store.close()
    except Exception:  # noqa: BLE001
        return {}


@router.post(
    "/indices/epfl_graph/search",
    response_model=IndexSearchResponse,
    response_model_exclude_none=True,
    tags=["Indices"],
)
async def epfl_graph_search_post(
    payload: IndexSearchRequest,
    request: Request,
    _token: Annotated[str, Depends(verify_token)],
) -> IndexSearchResponse | JSONResponse:
    """Semantic search against the EPFL Graph disciplines ontology."""
    return await _search_response_or_unavailable(
        await run_epfl_graph_search(payload, request.app.state),
        index_name="epfl_graph",
    )


@router.post(
    "/indices/zenodo_communities/search",
    response_model=IndexSearchResponse,
    response_model_exclude_none=True,
    tags=["Indices"],
)
async def zenodo_communities_search_post(
    payload: IndexSearchRequest,
    request: Request,
    _token: Annotated[str, Depends(verify_token)],
) -> IndexSearchResponse | JSONResponse:
    """Lexical (ILIKE) search against the institutional Zenodo communities
    registry.

    No semantic infrastructure — zenodo_communities is a tiny ~469-row
    DuckDB-only registry where substring scans across `title` /
    `description` / `keywords` finish in milliseconds. Title hits
    outrank description hits outrank keyword hits.
    """
    return await _search_response_or_unavailable(
        await run_communities_search(payload, request.app.state),
        index_name="zenodo_communities",
    )


# --- /v2/indices/gitlab_* -------------------------------------------------
# All nine gitlab stores share uniform leaf entrypoints, so their ingest +
# search endpoints are registered by a loop + factory over GITLAB_INDEX_NAMES
# rather than 18 hand-written handlers. `index_name` is bound per-iteration via
# a default arg inside each factory to avoid the late-binding closure bug.


def _make_gitlab_ingest_handler(index_name: str):
    async def gitlab_ingest_post(
        payload: GitLabIngestRequest,
        request: Request,
        _token: Annotated[str, Depends(verify_token)],
    ) -> IndexIngestJobAccepted | JSONResponse:
        """Enqueue a full-instance crawl + embed for this gitlab store."""
        job_store = _resolve_index_ingest_job_store(request)
        if job_store is None:
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content={
                    "detail": (
                        "index ingest job store unavailable: "
                        "provider cache is disabled"
                    ),
                },
            )
        job_id = str(uuid4())
        submitted_at = datetime.now(timezone.utc)
        job = IndexIngestJob(
            job_id=job_id, index_name=index_name,
            status=IndexIngestJobStatus.PENDING,
            request=payload.model_dump(mode="json"), submitted_at=submitted_at,
        )
        job_store.set(job)
        task = asyncio.create_task(
            run_gitlab_ingest_job(
                index_name=index_name, payload=payload,
                app_state=request.app.state, job_store=job_store, job_id=job_id,
            ),
        )
        _track_background_task(request, task)
        logger.info(
            "%s ingest job submitted: job_id=%s limit=%s",
            index_name, job_id, payload.limit,
        )
        return IndexIngestJobAccepted(
            job_id=job_id, index_name=index_name,
            status=IndexIngestJobStatus.PENDING,
            status_url=_index_job_status_path(job_id), submitted_at=submitted_at,
        )

    return gitlab_ingest_post


def _make_gitlab_search_handler(index_name: str):
    async def gitlab_search_post(
        payload: IndexSearchRequest,
        request: Request,
        _token: Annotated[str, Depends(verify_token)],
    ) -> IndexSearchResponse | JSONResponse:
        """Semantic search against this gitlab store."""
        return await _search_response_or_unavailable(
            await run_gitlab_search(index_name, payload, request.app.state),
            index_name=index_name,
        )

    return gitlab_search_post


for _gitlab_name in GITLAB_INDEX_NAMES:
    router.add_api_route(
        f"/indices/{_gitlab_name}/ingest",
        _make_gitlab_ingest_handler(_gitlab_name),
        methods=["POST"],
        response_model=IndexIngestJobAccepted,
        response_model_exclude_none=True,
        status_code=status.HTTP_202_ACCEPTED,
        tags=["Indices"],
        name=f"{_gitlab_name}_ingest_post",
        summary=f"Ingest the {_gitlab_name} store (full-instance crawl + embed)",
    )
    router.add_api_route(
        f"/indices/{_gitlab_name}/search",
        _make_gitlab_search_handler(_gitlab_name),
        methods=["POST"],
        response_model=IndexSearchResponse,
        response_model_exclude_none=True,
        tags=["Indices"],
        name=f"{_gitlab_name}_search_post",
        summary=f"Semantic search against the {_gitlab_name} store",
    )


# --- /v2/indices/freshness ------------------------------------------------
# Single roll-up over every supported catalog's `last_updated` for the Hub
# Overview / monitoring. One round-trip instead of 14 separate stats calls.


class _CatalogFreshness(BaseModel):
    provider: str
    count: int
    last_updated: datetime | None = None
    age_seconds: float | None = Field(
        default=None,
        description=(
            "Seconds since `last_updated`. `null` when the catalog is empty "
            "or has no timestamp-like column to read from."
        ),
    )


class _FreshnessResponse(BaseModel):
    as_of: datetime
    catalogs: list[_CatalogFreshness]
    oldest_provider: str | None = None
    oldest_age_seconds: float | None = None


@router.get(
    "/indices/freshness",
    response_model=_FreshnessResponse,
    response_model_exclude_none=True,
    tags=["Indices"],
)
async def index_freshness_get(
    request: Request,
    _token: Annotated[str, Depends(verify_token)],
) -> _FreshnessResponse:
    """Aggregate `last_updated` across every supported catalog.

    Returns one row per provider plus the `oldest_provider` / `oldest_age_seconds`
    convenience fields that Open Pulse Hub can alert on directly. Providers
    whose resources are unavailable on this deployment surface with
    `count=0, last_updated=null` so the response shape is uniform.
    """
    now = datetime.now(timezone.utc)

    def _one(provider: str) -> _CatalogFreshness:
        try:
            store = fetch_store_for_stats(provider, request.app.state)
        except UnknownIndexProviderError:
            return _CatalogFreshness(provider=provider, count=0)
        if store is None:
            return _CatalogFreshness(provider=provider, count=0)
        try:
            stats = collect_index_stats(provider, store.connect())
        except Exception:
            logger.exception("index freshness: %s collect failed", provider)
            return _CatalogFreshness(provider=provider, count=0)
        if stats.last_updated is None:
            return _CatalogFreshness(provider=provider, count=stats.count)
        # Both sides timezone-aware (collect_index_stats normalises to UTC).
        age = (now - stats.last_updated).total_seconds()
        return _CatalogFreshness(
            provider=provider,
            count=stats.count,
            last_updated=stats.last_updated,
            age_seconds=age,
        )

    catalogs = await asyncio.to_thread(
        lambda: [_one(p) for p in INDEX_STATS_SUPPORTED_PROVIDERS],
    )
    aged = [c for c in catalogs if c.age_seconds is not None]
    oldest = max(aged, key=lambda c: c.age_seconds) if aged else None
    return _FreshnessResponse(
        as_of=now,
        catalogs=catalogs,
        oldest_provider=oldest.provider if oldest else None,
        oldest_age_seconds=oldest.age_seconds if oldest else None,
    )


# --- /v2/indices/<name>/compact -------------------------------------------
# Operator endpoint: EXPORT/IMPORT round-trip the per-provider DuckDB
# file to reclaim space tombstoned by upsert churn. Mirrors what
# `just compact-indexes` does offline, but online and per-provider.


@router.post(
    "/indices/{provider}/compact",
    response_model=CompactResult,
    response_model_exclude_none=True,
    tags=["Indices"],
)
async def index_compact_post(
    provider: Annotated[str, Path(description="One of the supported index providers.")],
    request: Request,
    _token: Annotated[str, Depends(verify_token)],
) -> CompactResult | JSONResponse:
    """Run an EXPORT/IMPORT round-trip on `provider`'s DuckDB.

    Closes the in-process Store cached on `app.state` so the file lock
    is released, then opens a fresh connection, exports every table to
    a sibling tempdir, swaps the DuckDB atomically with a `.bak`
    fallback, and reports `bytes_before` / `bytes_after`. The next
    stats / search call lazily re-opens.

    This is a maintenance operation — call when the server is quiet.
    `openalex` (3.7 GB) can take a couple of minutes.
    """
    try:
        store = fetch_store_for_stats(provider, request.app.state)
    except UnknownIndexProviderError as exc:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"detail": str(exc)},
        )
    if store is None:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "detail": f"{provider} index resources unavailable on this deployment",
            },
        )
    db_path = getattr(store, "db_path", None)
    if db_path is None:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "detail": f"{provider} Store does not expose `db_path`; compact unsupported",
            },
        )
    # Close any in-process write handle so EXPORT can re-open the file.
    close_cached_resources_for(provider, request.app.state)
    try:
        result = await asyncio.to_thread(compact_duckdb, provider, db_path)
    except FileNotFoundError as exc:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"detail": str(exc)},
        )
    except Exception as exc:
        logger.exception("index compact failed: provider=%s", provider)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": f"compact failed: {exc}"},
        )
    return result


@router.get(
    "/indices/{provider}/stats",
    response_model=IndexStatsResponse,
    response_model_exclude_none=True,
    tags=["Indices"],
)
async def index_stats_get(
    provider: Annotated[str, Path(description="One of the supported index providers.")],
    request: Request,
    _token: Annotated[str, Depends(verify_token)],
) -> IndexStatsResponse | JSONResponse:
    """Read-only catalog stats: total rows + per-table breakdown + last_updated.

    External consumers (Open Pulse Hub Overview, dashboards) used to poll
    each `.duckdb` file with `duckdb.connect(path, read_only=True)`. That
    fails as soon as the GME holds a write connection (auto-ingest et al)
    because DuckDB's advisory lock is per-process. This endpoint runs the
    same `SELECT COUNT(*)` queries on the GME's already-open connection,
    so the file lock is never contested.
    """

    try:
        store = fetch_store_for_stats(provider, request.app.state)
    except UnknownIndexProviderError as exc:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"detail": str(exc)},
        )
    if store is None:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "detail": f"{provider} index resources unavailable on this deployment",
            },
        )

    try:
        stats = await asyncio.to_thread(
            collect_index_stats, provider, store.connect(),
        )
    except Exception as exc:
        logger.exception("index stats query failed: provider=%s", provider)
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"detail": f"stats query failed: {exc}"},
        )
    return stats


@router.get(
    "/indices/jobs/{job_id}",
    response_model=IndexIngestJob,
    response_model_exclude_none=True,
    tags=["Indices"],
)
async def index_ingest_job_status(
    job_id: Annotated[str, Path(description="Job id returned by an index ingest POST.")],
    request: Request,
    _token: Annotated[str, Depends(verify_token)],
) -> IndexIngestJob | JSONResponse:
    """Retrieve the status (and summary, when complete) of an index-ingest job."""

    job_store = _resolve_index_ingest_job_store(request)
    if job_store is None:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "detail": "index ingest job store unavailable: provider cache is disabled",
            },
        )

    record = job_store.get(job_id)
    if record is None:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"detail": f"no index ingest job found with id '{job_id}'"},
        )
    return record


# --- /v2/indices/<provider>/reset ----------------------------------------
# Cold-start a single provider's index: wipe DuckDB + Qdrant collection(s).
# The opt-in `wipe_cache=true` query param also clears the per-provider
# ProviderCache so re-ingest re-fetches from upstream instead of replaying
# cached responses. Token-gated; intentionally not idempotent-on-DELETE
# at the HTTP level (200 + structured result), since clients usually want
# to know what was actually reclaimed.


@router.delete(
    "/indices/{provider}/reset",
    tags=["Indices"],
    response_model=None,
)
async def reset_provider_index(
    provider: str,
    request: Request,
    _token: Annotated[str, Depends(verify_token)],
    wipe_qdrant: bool = True,
    wipe_cache: bool = False,
) -> dict[str, Any] | JSONResponse:
    """Wipe one provider's DuckDB + Qdrant collection(s), enabling a
    cold-start re-ingest.

    Query flags:
      - ``wipe_qdrant=true|false`` (default true): drop Qdrant
        collections too. Set false for a DuckDB-only reset.
      - ``wipe_cache=true|false`` (default false): also clear the
        per-provider ProviderCache. Use when upstream data has
        shifted; default keeps cached upstream responses so
        re-ingest is fast.
    """
    from open_pulse_sources.service.indices.reset import (  # noqa: PLC0415
        UnknownProviderError,
        reset_index,
    )

    try:
        result = await asyncio.to_thread(
            reset_index,
            provider,
            app_state=request.app.state,
            wipe_qdrant=wipe_qdrant,
            wipe_cache=wipe_cache,
        )
    except UnknownProviderError as exc:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"detail": str(exc)},
        )
    return {
        "provider": result.provider,
        "duckdb_deleted": result.duckdb_deleted,
        "duckdb_bytes_reclaimed": result.duckdb_bytes_reclaimed,
        "qdrant_collections_attempted": list(result.qdrant_collections_attempted),
        "qdrant_collections_dropped": list(result.qdrant_collections_dropped),
        "qdrant_skipped": result.qdrant_skipped,
        "cache_cleared": result.cache_cleared,
        "elapsed_seconds": result.elapsed_seconds,
    }


@router.delete(
    "/indices/reset-all",
    tags=["Indices"],
)
async def reset_all_indices(
    request: Request,
    _token: Annotated[str, Depends(verify_token)],
    wipe_qdrant: bool = True,
    wipe_cache: bool = False,
) -> dict[str, Any]:
    """Wipe every known provider in one call.

    Failures on individual providers don't stop the rest; each provider
    returns its own result entry. Use carefully — this is an operator
    tool for full re-ingest, not a routine cache flush.
    """
    from open_pulse_sources.service.indices.reset import reset_all  # noqa: PLC0415

    results = await asyncio.to_thread(
        reset_all,
        app_state=request.app.state,
        wipe_qdrant=wipe_qdrant,
        wipe_cache=wipe_cache,
    )
    return {
        "count": len(results),
        "results": [
            {
                "provider": r.provider,
                "duckdb_deleted": r.duckdb_deleted,
                "duckdb_bytes_reclaimed": r.duckdb_bytes_reclaimed,
                "qdrant_collections_dropped": list(r.qdrant_collections_dropped),
                "qdrant_skipped": r.qdrant_skipped,
                "cache_cleared": r.cache_cleared,
                "elapsed_seconds": r.elapsed_seconds,
            }
            for r in results
        ],
    }

