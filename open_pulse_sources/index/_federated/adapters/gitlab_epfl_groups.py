"""Adapter wrapping `open_pulse_sources.index.gitlab_epfl_groups` for federated search/lookup."""

from __future__ import annotations

from typing import Any

from open_pulse_sources.index._federated.registry import EntityRecord, Hit, register


class GitLabEpflGroupsAdapter:
    name = "gitlab_epfl_groups"
    entity_types: list[str] = ["group"]

    # Manifest hints (see IndexAdapter docstring).
    backend = "vector"
    surface_as_source = True
    id_shape = "url"  # group_id is already the canonical https://gitlab.epfl.ch/groups/... URL

    def search(
        self,
        *,
        query: str,
        entity_type: str | None,
        top_k: int,
        filters: dict[str, Any] | None,
    ) -> list[Hit]:
        try:
            from open_pulse_sources.index.gitlab_epfl_groups.retrieval import (
                search,
            )
        except Exception:
            return []
        try:
            results = search(query, top_k=top_k)
        except Exception:
            return []
        out: list[Hit] = []
        for r in results:
            payload = r.get("payload") or {}
            group_id = payload.get("group_id") or payload.get("entity_id")
            if not group_id:
                continue
            out.append(Hit(
                index=self.name,
                entity_type="group",
                id=str(group_id),
                title=payload.get("description") or str(group_id),
                score=float(r.get("rerank_score") or r.get("vector_score") or 0.0),
                summary=_summary(payload),
                url=str(group_id),
                payload=payload,
            ))
        return out

    def lookup(self, identifier: str) -> list[EntityRecord]:
        if not isinstance(identifier, str) or not identifier.strip():
            return []
        s = identifier.strip()
        # Validate that it's a GitLab group URL using the canonicalization helper.
        try:
            from open_pulse_sources.common.canonicalization.gitlab import (
                parse_gitlab_iri,
            )
        except Exception:
            return []
        parsed = parse_gitlab_iri(s)
        if parsed is None:
            return []
        host, _kind, _path = parsed
        if host != "gitlab.epfl.ch":
            return []
        try:
            from open_pulse_sources.index.gitlab_epfl_groups.store import (
                open_store,
            )
        except Exception:
            return []
        store = None
        try:
            store = open_store()
            row = store.fetch_group(s)
            if row is None:
                return []
            return [EntityRecord(
                index=self.name,
                entity_type="group",
                id=s,
                data=row,
                url=s,
            )]
        except Exception:
            return []
        finally:
            if store is not None:
                try:
                    store.close()
                except Exception:
                    pass


def _summary(payload: dict[str, Any]) -> str | None:
    parts = [
        str(payload.get("description") or ""),
        str(payload.get("full_path") or ""),
        str(payload.get("visibility") or ""),
    ]
    parts = [p for p in parts if p]
    return " — ".join(parts) if parts else None


register(GitLabEpflGroupsAdapter())
