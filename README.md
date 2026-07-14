# open-pulse-sources

[![CI](https://github.com/sdsc-ordes/open-pulse-sources/actions/workflows/ci.yml/badge.svg)](https://github.com/sdsc-ordes/open-pulse-sources/actions/workflows/ci.yml)

RAG source indices for the **Open Pulse** ecosystem — the *write side* of the
retrieval stack used by
[git-metadata-extractor](https://github.com/Imaging-Plaza/git-metadata-extractor)
(GME), plus the **index management API** that serves ingest / search / stats /
reset for every index.

## What lives here

Each index under `open_pulse_sources/index/<name>/` is an independent pipeline:

```
upstream API → ingest CLI → DuckDB (<INDEX_DATA_DIR>/<name>/duckdb/)
             → embed CLI  → RCP embeddings → Qdrant collection(s)
             → search CLI / management API (vector + RCP rerank)
```

Covered sources: GitHub (repos/users/orgs), GitLab (EPFL/ETHZ/data-science
instances), HuggingFace (models/datasets/spaces/papers/users/orgs), OpenAlex,
ORCID, ROR, Zenodo (records/communities), Infoscience, ETHZ Research
Collection, SNSF, SWISSUbase, RenkuLab, DockerHub, OA Monitor, EPFL Graph
disciplines — plus a **federated** cross-index search layer
(`open_pulse_sources/index/_federated/`).

Shared infrastructure:

- **Storage** — DuckDB per index (canonical records + `chunks` ledger), with
  atomic read-only snapshot publication (`_snapshot.py`) for cross-process
  readers.
- **Vectors** — Qdrant, per-index collections, cosine, 4096-dim.
- **Embeddings / rerank** — `Qwen/Qwen3-Embedding-8B` / `Qwen3-Reranker-8B`
  on EPFL RCP (`RCP_TOKEN` required).
- **Chunking** — token-aware sliding window (`tiktoken`, `cl100k_base`).

## The management API

`open_pulse_sources.service.app:app` (FastAPI) serves the surface the GME
monolith used to own — routes keep the `/v2` prefix so existing consumers
only change the host:

| Route family | Purpose |
|---|---|
| `GET /health` | liveness (open, no auth) |
| `GET /v2/manifest` | federated store manifest — the contract consumers build against |
| `POST /v2/indices/<name>/ingest` | async ingest job (`202` + job id; poll `GET /v2/indices/jobs/{id}`) |
| `POST /v2/indices/<name>/search` | semantic search (vector + rerank) |
| `GET /v2/indices/<name>/stats` | row counts + freshness without contesting DuckDB locks |
| `GET /v2/indices/freshness` | staleness overview across catalogs |
| `POST /v2/indices/<name>/compact` / `DELETE .../reset` / `DELETE /v2/indices/reset-all` | maintenance (destructive ops are token-gated like everything else) |

Auth: every route except `/` and `/health` requires
`Authorization: Bearer <API_TOKEN>` and **fails closed** when `API_TOKEN` is
unset.

## Quickstart (local development)

```bash
cp .env.example .env          # fill in API_TOKEN (+ RCP_TOKEN for search/embed)
just install-dev              # uv pip install -e ".[dev]"
just test                     # non-live test suite
just serve-dev                # management API on :8080 with reload

# per-index CLIs (ingest / embed / search / status), e.g.:
just openalex-ingest --scope epfl
just openalex-embed
just openalex-search "geospatial machine learning"
just gme-search "protein folding tools"      # federated, across all indices
```

`just --list` shows every recipe. Static import guard:
`python scripts/check_import_closure.py`.

## Docker / compose

```bash
just docker-build             # tools/image/Dockerfile → open-pulse-sources
just compose-up               # standalone stack: ops-sources + ops-qdrant + ops-selenium
```

- **Standalone stack** (`tools/deploy/docker-compose.yml`): run the index
  service on its own host.
- **Combined stack**: when deploying next to the extractor, use GME's
  `tools/deploy/docker-compose.yml` instead — its `gme-sources` service runs
  this image sharing the `gme-data` volume (DuckDB stores) and Qdrant with
  the extraction API.
- **Published image**: CI pushes `ghcr.io/sdsc-ordes/open-pulse-sources`
  (`latest` from `main`, branch tags, `sha-*` tags for pinning). Both compose
  stacks default to it via `SOURCES_IMAGE`. Note: the GHCR package must be
  made public once (or deploy hosts `docker login ghcr.io`).

## Configuration

Key environment variables (full annotated list in
[`.env.example`](.env.example)):

| Var | Purpose |
|---|---|
| `API_TOKEN` | bearer auth for the API — required, fails closed |
| `RCP_TOKEN` | RCP embeddings/rerank — required for embed + search |
| `INDEX_QDRANT_URL` | Qdrant endpoint (compose sets it per network) |
| `INDEX_DATA_DIR` | root of the DuckDB stores — **set explicitly in containers** (`/app/data/index`); the fallback is repo-checkout-relative |
| `GME_GITHUB_TOKEN`, `HF_TOKEN`, `GITLAB_{EPFL,ETHZ,DATASCIENCE}_TOKEN`, … | per-source ingest credentials, only for indices you ingest (see `.env.example`) |
| `SELENIUM_REMOTE_URL` | Selenium grid for SWISSUbase/ORCID-scraping ingest |

## Relationship to git-metadata-extractor

GME consumes this repo two ways:

1. **As a Python library** (`open_pulse_sources`) — its read-side RAG
   providers import the retrieval layer (Qdrant stores, RCP clients,
   configs, DuckDB readers) directly. Treat module paths GME imports as
   semi-public API: do not move them without checking GME first.
2. **As a service** — the routes above, plus the shared runtime contract:
   Qdrant collection names + payload shapes, `<INDEX_DATA_DIR>/<name>/`
   store paths and `.ro.duckdb` snapshots, and RCP endpoints.

The split from the GME monolith (completed 2026-07-02, code extracted at
GME commit `64f1d14`) is documented in the GME repository — see its
`CHANGELOG.md` and the hardening task briefs under
`dev/split-rag-indices/`. [`AGENTS.md`](AGENTS.md) is the operating guide
for coding agents working in this repo.

## Repository layout

```
open_pulse_sources/
  index/        per-index pipelines + _federated/, _rcp/, _shared/, _snapshot
  service/      FastAPI management API (api, app, auth, api_models, indices/)
  common/       shared helpers copied from GME v2 (canonicalization, cache, …)
  module/       dependents scraper + EPFL Graph client
config/
  index/        per-index YAML defaults (deploy values env-overridable)
  seeds/        seed identifier lists for the reingest driver ($SEEDS_DIR overrides)
scripts/        ops tooling (reingest, monolith→split migration, guards)
tests/          index/ + service/ suites (non-live by default)
tools/          Docker image + compose stack
docs/           per-index documentation (start at docs/rag-indices.md)
```

## License

[Apache-2.0](LICENSE) — inherited from git-metadata-extractor, from which
this code was extracted (@ `64f1d14`, 2026-07-02).
