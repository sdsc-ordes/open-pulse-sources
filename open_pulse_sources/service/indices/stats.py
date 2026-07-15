"""Read-only catalog stats for `GET /v2/indices/{provider}/stats`.

External consumers (Open Pulse Hub's Overview charts, dashboards) used to
poll each `.duckdb` file directly with `duckdb.connect(path, read_only=True)`.
That stopped working the moment the GME started auto-ingesting concurrently
— DuckDB takes an advisory file lock even in read-only mode, and a reader
colliding with the GME's writer gets `Could not set lock on file ...
Conflicting lock is held in PID 0`. So we expose the same numbers
through the API process that already owns the open connection.

Implementation is intentionally schema-agnostic: we list user tables via
`information_schema.tables`, run `SELECT COUNT(*)` on each, and pick a
`last_updated` from whichever timestamp column happens to be present.
This means adding a new provider (or a new table inside a provider's
DuckDB) doesn't need a code change here.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    import duckdb

INDEX_STATS_SUPPORTED_PROVIDERS: tuple[str, ...] = (
    # Providers that already have a v2 ingest/search surface and a
    # long-lived `get_or_create_<provider>_resources()` cache on `app_state`.
    "zenodo_records",
    "github_repos",
    "huggingface_models",
    "huggingface_datasets",
    "huggingface_spaces",
    "huggingface_users",
    "huggingface_organizations",
    "openalex",
    "orcid",
    "renkulab",
    "swissubase",
    "ethz_research_collection",
    "oamonitor",
    # CLI-managed catalogs (no v2 ingest/search route). We open their
    # DuckDB on demand and cache on `app_state.v2_<provider>_store` so
    # subsequent stats polls reuse the open connection.
    "ror",
    "infoscience",
    "snsf",
    "epfl_graph",
    "zenodo_communities",
)

# Common "this row was last touched" column names, in priority order.
# First one present per table wins. Extend as new schemas show up.
_TIMESTAMP_COLUMN_CANDIDATES: tuple[str, ...] = (
    "updated_at",
    "ingested_at",
    "fetched_at",
    "updated",
    "pushed_at",
    "created_at",
)


class IndexStatsResponse(BaseModel):
    """Read-only catalog stats response shape."""

    provider: str = Field(..., description="One of INDEX_STATS_SUPPORTED_PROVIDERS.")
    count: int = Field(..., ge=0, description="Total rows across every user table.")
    last_updated: datetime | None = Field(
        default=None,
        description=(
            "Most recent timestamp found in any timestamp-like column across "
            "all tables. `null` when the catalog is empty or no such column exists."
        ),
    )
    by_table: dict[str, int] = Field(
        default_factory=dict,
        description="Row count per user table, useful for multi-table catalogs.",
    )


class UnknownIndexProviderError(ValueError):
    """Raised when the URL provider isn't in INDEX_STATS_SUPPORTED_PROVIDERS."""


def _coerce_timestamp(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    return None


def collect_index_stats(
    provider: str,
    conn: duckdb.DuckDBPyConnection,
) -> IndexStatsResponse:
    """Schema-introspect the DuckDB at `conn` and return its stats."""

    table_rows = conn.execute(
        """
        SELECT table_name
          FROM information_schema.tables
         WHERE table_schema = 'main' AND table_type = 'BASE TABLE'
         ORDER BY table_name
        """,
    ).fetchall()

    by_table: dict[str, int] = {}
    for (table_name,) in table_rows:
        count_row = conn.execute(
            f'SELECT COUNT(*) FROM "{table_name}"',
        ).fetchone()
        by_table[table_name] = int(count_row[0]) if count_row else 0

    last_updated: datetime | None = None
    for table_name in by_table:
        col_rows = conn.execute(
            """
            SELECT column_name FROM information_schema.columns
             WHERE table_schema = 'main' AND table_name = ?
            """,
            [table_name],
        ).fetchall()
        present = {row[0] for row in col_rows}
        for candidate in _TIMESTAMP_COLUMN_CANDIDATES:
            if candidate not in present:
                continue
            value_row = conn.execute(
                f'SELECT MAX("{candidate}") FROM "{table_name}"',
            ).fetchone()
            value = value_row[0] if value_row else None
            coerced = _coerce_timestamp(value)
            if coerced is not None and (
                last_updated is None or coerced > last_updated
            ):
                last_updated = coerced
            break

    return IndexStatsResponse(
        provider=provider,
        count=sum(by_table.values()),
        last_updated=last_updated,
        by_table=by_table,
    )


def fetch_store_for_stats(provider: str, app_state: Any) -> Any | None:
    """Return the long-lived DuckDB-backed Store for `provider`, or None.

    Reuses the existing `get_or_create_<provider>_resources` helpers so we
    share the writer's open connection and avoid the cross-process lock
    fight. ETHZ has no long-lived store on `app_state`, so we open one
    on demand for the read.
    """

    if provider not in INDEX_STATS_SUPPORTED_PROVIDERS:
        raise UnknownIndexProviderError(
            f"unknown index provider: {provider!r}; "
            f"supported: {', '.join(INDEX_STATS_SUPPORTED_PROVIDERS)}",
        )

    if provider == "github_repos":
        from open_pulse_sources.service.indices.github_repos import (
            get_or_create_github_repos_resources,
        )
        res = get_or_create_github_repos_resources(app_state)
        return res[1] if res else None
    if provider == "zenodo_records":
        from open_pulse_sources.service.indices.zenodo_records import (
            get_or_create_zenodo_records_store,
        )
        res = get_or_create_zenodo_records_store(app_state)
        return res[1] if res else None
    if provider == "huggingface_models":
        from open_pulse_sources.service.indices.huggingface_models import (
            get_or_create_huggingface_models_resources,
        )
        res = get_or_create_huggingface_models_resources(app_state)
        return res[1] if res else None
    if provider == "huggingface_datasets":
        from open_pulse_sources.service.indices.huggingface_datasets import (
            get_or_create_huggingface_datasets_resources,
        )
        res = get_or_create_huggingface_datasets_resources(app_state)
        return res[1] if res else None
    if provider == "huggingface_spaces":
        from open_pulse_sources.service.indices.huggingface_spaces import (
            get_or_create_huggingface_spaces_resources,
        )
        res = get_or_create_huggingface_spaces_resources(app_state)
        return res[1] if res else None
    if provider == "huggingface_users":
        from open_pulse_sources.service.indices.huggingface_users import (
            get_or_create_huggingface_users_resources,
        )
        res = get_or_create_huggingface_users_resources(app_state)
        return res[1] if res else None
    if provider == "huggingface_organizations":
        from open_pulse_sources.service.indices.huggingface_organizations import (
            get_or_create_huggingface_organizations_resources,
        )
        res = get_or_create_huggingface_organizations_resources(app_state)
        return res[1] if res else None
    if provider == "openalex":
        from open_pulse_sources.service.indices.openalex import (
            get_or_create_openalex_resources,
        )
        res = get_or_create_openalex_resources(app_state)
        return res[1] if res else None
    if provider == "orcid":
        from open_pulse_sources.service.indices.orcid import (
            get_or_create_orcid_resources,
        )
        res = get_or_create_orcid_resources(app_state)
        return res[1] if res else None
    if provider == "renkulab":
        from open_pulse_sources.service.indices.renkulab import (
            get_or_create_renkulab_resources,
        )
        res = get_or_create_renkulab_resources(app_state)
        return res[2] if res else None
    if provider == "swissubase":
        from open_pulse_sources.service.indices.swissubase import (
            get_or_create_swissubase_resources,
        )
        res = get_or_create_swissubase_resources(app_state)
        return res[2] if res else None
    if provider == "oamonitor":
        from open_pulse_sources.service.indices.oamonitor import (
            get_or_create_oamonitor_resources,
        )
        res = get_or_create_oamonitor_resources(app_state)
        return res[2] if res else None
    if provider == "ethz_research_collection":
        try:
            from open_pulse_sources.index.ethz_research_collection.storage import (
                EthzResearchCollectionStore,
            )
        except Exception:
            return None
        try:
            return EthzResearchCollectionStore.open()
        except Exception:
            return None

    # CLI-managed catalogs: no v2 ingest/search route → no
    # `get_or_create_*_resources` helper. Open once, cache on `app_state`.
    if provider == "ror":
        return _cli_store(
            app_state, "v2_ror_store",
            "open_pulse_sources.index.ror.storage.duckdb_store", "RorStore",
        )
    if provider == "infoscience":
        return _cli_store(
            app_state, "v2_infoscience_store",
            "open_pulse_sources.index.infoscience.storage.duckdb_store", "InfoscienceStore",
        )
    if provider == "snsf":
        return _cli_store(
            app_state, "v2_snsf_store",
            "open_pulse_sources.index.snsf.storage.duckdb_store", "SnsfStore",
        )
    if provider == "epfl_graph":
        return _open_epfl_graph_store_readonly(app_state)
    if provider == "zenodo_communities":
        return _open_communities_store(app_state)
    return None


def _open_epfl_graph_store_readonly(app_state: Any) -> Any | None:
    """Open the epfl_graph stats store READ-ONLY and cache it on app_state.

    Stats runs only ``COUNT(*)`` selects, so it never needs write access. A
    read-write handle cached here is long-lived and collides with the read-only
    disciplines lookup during concurrent extraction (Bug 01), so the resident
    handle must be read-only. Skipped when the DB file is absent — a read-only
    open cannot create it (and there would be nothing to count anyway)."""
    cached = getattr(app_state, "v2_epfl_graph_store", None)
    if cached is not None:
        return cached
    try:
        from open_pulse_sources.index.epfl_graph.paths import (
            get_epfl_graph_paths,
        )
        from open_pulse_sources.index.epfl_graph.storage.duckdb_store import (
            EpflGraphStore,
        )

        db_path = get_epfl_graph_paths().duckdb_path
        if not db_path.exists():
            return None
        store = EpflGraphStore.open_readonly(db_path)
    except Exception:
        return None
    try:
        app_state.v2_epfl_graph_store = store
    except Exception:
        return store
    return store


def _cli_store(
    app_state: Any, attr: str, module: str, class_name: str,
) -> Any | None:
    """Lazy-open a CLI-managed Store and cache it on `app_state.<attr>`."""
    cached = getattr(app_state, attr, None)
    if cached is not None:
        return cached
    try:
        mod = __import__(module, fromlist=[class_name])
        store_cls = getattr(mod, class_name)
    except Exception:
        return None
    try:
        store = store_cls.open()
    except Exception:
        return None
    try:
        setattr(app_state, attr, store)
    except Exception:
        return store
    return store


def _open_communities_store(app_state: Any) -> Any | None:
    """`ZenodoCommunitiesStore` lacks `.connect()` (uses `_connect()` + `read_only()`),
    so the stats endpoint can't call it directly. Wrap it in a tiny shim that
    exposes a cached read-only handle as `.connect()`.
    """
    cached = getattr(app_state, "v2_zenodo_communities_store", None)
    if cached is not None:
        return cached
    try:
        import duckdb as _duckdb

        from open_pulse_sources.index.zenodo_communities.paths import (
            duckdb_path,
        )
    except Exception:
        return None

    class _ZenodoCommunitiesStoreShim:
        def __init__(self, path: Any) -> None:
            self.db_path = path  # surfaced for compact_duckdb()
            self._conn: Any = None

        def connect(self) -> Any:
            if self._conn is None:
                self._conn = _duckdb.connect(str(self.db_path), read_only=True)
            return self._conn

        def close(self) -> None:
            if self._conn is not None:
                self._conn.close()
                self._conn = None

    try:
        shim = _ZenodoCommunitiesStoreShim(duckdb_path())
    except Exception:
        return None
    try:
        app_state.v2_zenodo_communities_store = shim
    except Exception:
        return shim
    return shim


__all__ = [
    "INDEX_STATS_SUPPORTED_PROVIDERS",
    "IndexStatsResponse",
    "UnknownIndexProviderError",
    "collect_index_stats",
    "fetch_store_for_stats",
]
