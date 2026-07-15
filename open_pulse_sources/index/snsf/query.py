"""Public query API for the SNSF P3 index.

`query_rag` runs Qdrant retrieval (embedded scope subset) → reranks via the
RCP cross-encoder → returns the top hits hydrated from the Qdrant payload.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import numpy as np

from open_pulse_sources.index.snsf.config import SnsfIndexConfig
from open_pulse_sources.index.snsf.embed import embed_query
from open_pulse_sources.index.snsf.qdrant_store import QdrantSnsfStore
from open_pulse_sources.index.snsf.rerank import rerank

logger = logging.getLogger(__name__)


async def query_rag(
    cfg: SnsfIndexConfig,
    text: str,
    *,
    top_k: int | None = None,
    rerank_top_k: int | None = None,
    institution: str | None = None,
    institute: str | None = None,
    discipline_l1: str | None = None,
    state: str | None = None,
    scope_mode: str | None = None,
) -> list[dict[str, Any]]:
    if cfg.rcp.token is None:
        msg = "RCP_TOKEN is not set."
        raise RuntimeError(msg)
    top_k = top_k or cfg.retrieval.top_k
    rerank_top_k = rerank_top_k or cfg.retrieval.rerank_top_k
    active = scope_mode or cfg.scope.active

    qvec = await embed_query(cfg.rcp, text, normalize=True)
    qstore = QdrantSnsfStore(cfg)
    candidates = qstore.search(
        active,
        # Inflate top_k when --institute post-filter is set — most candidates
        # will be discarded so we need a wider net to keep `rerank_top_k` non-empty.
        query_vector=np.asarray(qvec, dtype=np.float32).tolist(),
        top_k=top_k * 4 if institute else top_k,
        institution=institution,
        discipline_l1=discipline_l1,
        state=state,
    )
    if not candidates:
        return []

    if institute:
        candidates = _post_filter_by_institute(candidates, institute)
        if not candidates:
            return []

    rerank_results = await rerank(
        cfg.rcp, text, [c["text"] for c in candidates], top_n=rerank_top_k,
    )
    out: list[dict[str, Any]] = []
    for r in rerank_results[:rerank_top_k]:
        if r.index < 0 or r.index >= len(candidates):
            continue
        c = candidates[r.index]
        out.append({**c, "score": float(r.score)})
    return out


def _post_filter_by_institute(
    candidates: list[dict[str, Any]],
    institute_substring: str,
) -> list[dict[str, Any]]:
    """Keep only candidates whose `institute` (lab/centre, from DuckDB) matches.

    `institute` isn't in the Qdrant payload (it would balloon every point),
    so we resolve it from DuckDB after the ANN. Substring match, case-folded.
    """
    from open_pulse_sources.index.snsf.storage.duckdb_store import SnsfStore

    needle = institute_substring.lower()
    grant_ids = [c["grant_number"] for c in candidates]
    if not grant_ids:
        return []
    store = SnsfStore.open()
    try:
        placeholders = ",".join(["?"] * len(grant_ids))
        rows = store.connect().execute(
            f"SELECT grant_number, institute FROM grants "
            f"WHERE grant_number IN ({placeholders})",
            list(grant_ids),
        ).fetchall()
    finally:
        store.close()

    institute_by_id = {gn: (inst or "") for gn, inst in rows}
    kept = []
    for c in candidates:
        inst = institute_by_id.get(c["grant_number"], "")
        if needle in inst.lower():
            kept.append({**c, "institute": inst})
    return kept


def query_rag_sync(cfg: SnsfIndexConfig, text: str, **kwargs: Any) -> list[dict[str, Any]]:
    return asyncio.run(query_rag(cfg, text, **kwargs))


__all__ = ["query_rag", "query_rag_sync"]
