# Agent Operating Guide for open-pulse-sources

Operating contract for autonomous and semi-autonomous coding agents working
in this repository. Goal: safe, reproducible contributions with minimal
human back-and-forth.

## What this repo is

The **RAG source-index layer** of the Open Pulse ecosystem: ingest → DuckDB
→ embed → Qdrant pipelines for ~30 scholarly/code sources, a federated
cross-index search layer, and a FastAPI **management API**
(`/v2/manifest` + `/v2/indices/*`). It was split out of the
`git-metadata-extractor` (GME) monolith (2026-07-02, extracted at GME
commit `64f1d14`). The split record and its hardening backlog live in the
GME repository (`CHANGELOG.md` + `dev/split-rag-indices/`); skim them
before making structural changes here.

GME still consumes this repo **as an installed library** (its read-side RAG
providers import `open_pulse_sources.*` directly) and shares runtime state
with it (Qdrant collections, DuckDB stores). That creates cross-repo
contract obligations — see "Cross-repo contract" below.

## Code map

```
open_pulse_sources/
  index/
    <name>/                    one package per index. Typical anatomy:
      config.py                yaml loader (config/index/<name>.yaml) + env overrides
      paths.py                 store paths under <INDEX_DATA_DIR>/<name>/
      ingest/                  upstream-API client + ingest pipeline
      storage/duckdb_store.py  canonical records + chunks ledger (+ schema.sql)
      embed/pipeline.py        chunk + RCP-embed + Qdrant upsert; collection names
      retrieval/               semantic search (vector + RCP rerank) + SQL reads
      _federated.py            adapter registration for the federated layer
    _federated/                cross-index search/entity/manifest/bootstrap
    _rcp/                      shared RCP embed/rerank clients
    _shared/                   small shared helpers (doi, …)
    _snapshot.py               atomic .ro.duckdb snapshot publication
    _github_accounts_base/, _gitlab_base/, _huggingface_base/   family bases
  service/
    app.py                     FastAPI entrypoint (uvicorn …service.app:app, :8080)
    api.py                     /v2/manifest + /v2/indices/* routes (verbatim from GME)
    auth.py                    bearer API_TOKEN, fails closed
    api_models.py              request/response contracts (batch + query caps)
    indices/                   per-index ingest/search runners, job store, stats,
                               compact, reset
  common/                      helpers copied from GME v2 (canonicalization,
                               ProviderCache, URL detection, ORCID stack).
                               GME keeps its own originals — do not assume sync.
  module/                      dependents scraper + EPFL Graph client

config/index/*.yaml            per-index config; resolved CWD-relative (known wart)
config/seeds/<name>.txt        seed lists for the reingest driver ($SEEDS_DIR overrides)
scripts/                       reingest driver, monolith→split migration,
                               check_import_closure.py (import guard)
tests/index/, tests/service/   the two suites; non-live by default
tools/image/Dockerfile         service image  ·  tools/deploy/  compose stack
```

## Commands

The `justfile` is the source of truth. Prefer `just <recipe>`.

| Recipe | Purpose |
|---|---|
| `just install-dev` | `uv pip install -e ".[dev]"` |
| `just test` | non-live test suite (xdist) |
| `just serve` / `serve-dev` | management API on :8080 |
| `just <prefix>-{ingest,embed,search,query,status,serve}` | per-index CLIs (`openalex-*`, `orcid-*`, `hf-*`, `epfl-graph-*`, `swissubase-*`, `renku-*`, `index-infoscience-*`, …) |
| `just gme-search` / `gme-entity` / `gme-indices` | federated layer CLI |
| `just docker-build` / `compose-up` / `compose-down` | image + standalone stack |
| `python scripts/check_import_closure.py` | every `open_pulse_sources.*` import resolves in-repo |

⚠ Known-stale recipes inherited from the monolith: `gh-*` and `zenodo-*`
target `index.github` / `index.zenodo`, which were renamed upstream to
`github_repos` / `zenodo_records` before the split. Fix or avoid.

## Configuration (env vars)

| Var | Default | Purpose |
|---|---|---|
| `API_TOKEN` | — | bearer auth for every route except `/` and `/health`. **Fails closed** (unset → 503). |
| `RCP_TOKEN` | — | RCP embeddings/rerank; required for embed pipelines and `/search`. Missing token currently surfaces as a raw 500 on search (known gap). |
| `INDEX_QDRANT_URL` | `http://qdrant:6333` (yaml) | Qdrant endpoint for every index |
| `INDEX_DATA_DIR` | `data/index` under the repo root | DuckDB store root. **Always set explicitly in containers/wheel installs** (`/app/data/index`) — the fallback resolves relative to the installed package (`site-packages/data` in a wheel). |
| `SELENIUM_REMOTE_URL` | unset | Selenium grid for SWISSUbase / ORCID-scraping ingest |
| `GME_GITHUB_TOKEN`, `HF_TOKEN`, `GITLAB_TOKEN`, `INFOSCIENCE_TOKEN`, `RENKULAB_TOKEN`, `EPFL_GRAPH_USERNAME/_PASSWORD` | unset | per-source ingest credentials |
| `V2_PROVIDER_CACHE_{PATH,TTL_DAYS,ENABLED}` | `.cache/v2/providers.db`, 30, true | provider/job cache. Names inherited from GME; rename planned pre-1.0. |

Rules: never print, log, or commit secrets. Never modify `.env` unless
explicitly asked. Fail fast naming the missing variable (never its value).

## Testing & CI

- `just test` runs both suites with `-m 'not live_provider and not
  llm_integration'`. Live-provider and LLM tests are opt-in markers.
- `tests/service/conftest.py` seeds `API_TOKEN` for route tests; index
  tests need no credentials.
- CI (`.github/workflows/ci.yml`): locked install → import-closure guard →
  non-live suite → Docker build → in-container smoke (`/health`,
  fail-closed auth, authenticated `/v2/manifest`) → publish to
  `ghcr.io/<owner>/open-pulse-sources` (`latest` from main, branch tags,
  `sha-*` for pinning). Lint/type gates are intentionally absent for now
  (~2k inherited ruff findings).

## Cross-repo contract (GME) — read before refactoring

1. **Module paths are semi-public API.** GME imports, among others:
   `index._rcp.*`, `index._shared.doi`, `index._federated.*`,
   `index.openalex.vector.qdrant_store`, per-index `config` /
   `embed.pipeline` (collection constants) / `storage.duckdb_store` /
   `paths`, `index.snsf.facet_query`. Renaming or moving these breaks the
   extractor at import time (or worse, silently — several GME providers
   swallow ImportError and disable themselves). Check GME's
   `grep -r "open_pulse_sources" src/` before moving anything.
2. **Runtime contract**: Qdrant collection names + payload shapes,
   `<INDEX_DATA_DIR>/<name>/duckdb/` paths and `.ro.duckdb` snapshots, RCP
   endpoints, and the `/v2` route prefix of the service API. Changing any
   of these requires a coordinated GME change and a compatibility note.
3. **Route compatibility**: `/v2/manifest` and `/v2/indices/*` must keep
   their paths/methods/status codes — GME's old consumers were repointed
   host-only.
4. DuckDB is effectively **single-writer per store file**: bulk ingest
   belongs to this service; GME may hold read connections and (opt-in)
   auto-ingest writers. Don't add new write paths without checking the
   single-writer plan in the GME repo (`dev/split-rag-indices/05-*.md`).

## Editing rules

- Keep diffs minimal and scoped; preserve existing style and conventions.
- Do not rename or move public modules (see contract above) without an
  explicit request.
- New runtime assets (`.sql`, `.yaml`, templates) currently do NOT ship in
  wheels (known P0 gap) — if you add one, extend the packaging fix, not
  just the source tree.
- Store schema changes must keep `storage/schema.sql`, the DuckDB store
  bootstrap, and existing on-disk stores compatible (or ship an explicit
  migration in `scripts/`).
- Destructive operations (reset, re-embed, store deletion) are
  operator-facing: never run them against non-temporary data in tests.

## Known gaps (do not re-discover)

Tracked as task briefs in the GME repo (`dev/split-rag-indices/`):
wheel package-data (01), unpublished release/pinning (02), lint/type CI
gates (03), cross-repo contract tests + stale HF config import (04),
single-writer boundary (05), snapshot read-path completion (06), migration
script hardening (07), config ownership + stale docs/recipes (08).

## Reporting contract

Completion reports must include: files changed, behavior change, commands
run + key results, risks/follow-ups. No vague "done" — verifiable evidence.
