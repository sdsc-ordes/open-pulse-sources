"""Adapter wrapping `open_pulse_sources.index.gitlab_epfl_users` for federated search/lookup."""

from __future__ import annotations

from typing import Any

from open_pulse_sources.index._federated.registry import EntityRecord, Hit, register


class GitLabEpflUsersAdapter:
    name = "gitlab_epfl_users"
    entity_types: list[str] = ["user"]

    # Manifest hints (see IndexAdapter docstring).
    backend = "vector"
    surface_as_source = True
    id_shape = "url"  # user_id is already the canonical https://gitlab.epfl.ch/<username> URL

    def search(
        self,
        *,
        query: str,
        entity_type: str | None,
        top_k: int,
        filters: dict[str, Any] | None,
    ) -> list[Hit]:
        try:
            from open_pulse_sources.index.gitlab_epfl_users.retrieval import (
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
            user_id = payload.get("user_id") or payload.get("entity_id")
            if not user_id:
                continue
            entity = r.get("entity") or {}
            out.append(Hit(
                index=self.name,
                entity_type="user",
                id=str(user_id),
                title=(entity.get("name") if entity else None) or str(user_id),
                score=float(r.get("rerank_score") or r.get("vector_score") or 0.0),
                summary=_summary(entity),
                url=str(user_id),
                payload=payload,
            ))
        return out

    def lookup(self, identifier: str) -> list[EntityRecord]:
        if not isinstance(identifier, str) or not identifier.strip():
            return []
        s = identifier.strip()
        # Validate that it's a GitLab user URL using the canonicalization helper.
        try:
            from open_pulse_sources.common.canonicalization.gitlab import (
                parse_gitlab_iri,
            )
        except Exception:
            return []
        parsed = parse_gitlab_iri(s)
        if parsed is None:
            return []
        host, kind, _path = parsed
        if kind != "user" or host != "gitlab.epfl.ch":
            return []
        try:
            from open_pulse_sources.index.gitlab_epfl_users.store import (
                open_store,
            )
        except Exception:
            return []
        store = None
        try:
            store = open_store()
            row = store.fetch_user(s)
            if row is None:
                return []
            return [EntityRecord(
                index=self.name,
                entity_type="user",
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


def _summary(entity: dict[str, Any]) -> str | None:
    parts = [
        str(entity.get("bio") or ""),
        str(entity.get("organization") or ""),
        str(entity.get("location") or ""),
    ]
    parts = [p for p in parts if p]
    return " — ".join(parts) if parts else None


register(GitLabEpflUsersAdapter())
