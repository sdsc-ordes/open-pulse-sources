# Changelog

All notable changes to this project will be documented in this file.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and the project uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- **Initial extraction from the `git-metadata-extractor` monolith**
  (@ `64f1d14`, 2026-07-02; the full phase record lives in the GME
  repository — `CHANGELOG.md` + `dev/split-rag-indices/`):
  - `open_pulse_sources/index/` — every RAG source index (ingest → DuckDB →
    embed → Qdrant) plus the federated cross-index layer.
  - `open_pulse_sources/service/` — the standalone management API
    (`/v2/manifest` + `/v2/indices/*` ingest/search/stats/compact/reset),
    route-compatible with what the monolith used to serve.
  - `open_pulse_sources/common/` — shared helpers (canonicalization,
    provider cache, URL detection, ORCID stack) copied from the monolith.
  - Tests (index + service suites), index docs, config (per-index yaml +
    seed lists under `config/seeds/`), ops scripts.
  - Docker image (`tools/image/Dockerfile`) and standalone compose stack
    (`tools/deploy/docker-compose.yml`).
  - CI (`.github/workflows/ci.yml`): non-live test suite, import-closure
    guard, image build + smoke + publish to GHCR.

### Known gaps (tracked in the parent repo, `dev/split-rag-indices/`)

- Wheels omit runtime `.sql`/`.yaml` package data — non-editable installs
  cannot bootstrap stores yet (the Docker image works via the copied
  source tree).
- `INDEX_DATA_DIR` must be set explicitly in containers; the fallback is
  package-relative.
- Some `justfile` recipes inherited from the monolith target renamed
  modules (`gh-*`, `zenodo-*`).
- `V2_*` cache env-var names are inherited; rename planned before 1.0.
