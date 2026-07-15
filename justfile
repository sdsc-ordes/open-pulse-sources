# Open Pulse Sources - Task Runner
# RAG source indices (ingest → DuckDB → embed → Qdrant) extracted from
# git-metadata-extractor. Usage: just <command>

# Auto-load .env so RCP_TOKEN / source tokens are visible to recipes.
set dotenv-load := true

# Default recipe - show available commands
default:
    @just --list

# ============================================================================
# Installation & Setup
# ============================================================================

# Install dependencies from pyproject.toml
install:
    uv pip install .

# Install in development mode with all dependencies
install-dev:
    uv pip install -e ".[dev]"

# ============================================================================
# Running the index service API
# ============================================================================

# Serve the index service (manifest + /v2/indices/* ingest/search/stats/reset)
serve *ARGS:
    .venv/bin/python -m uvicorn open_pulse_sources.service.app:app --host 0.0.0.0 --port 8080 {{ARGS}}

# Serve with auto-reload for development
serve-dev *ARGS:
    .venv/bin/python -m uvicorn open_pulse_sources.service.app:app --host 0.0.0.0 --port 8080 --reload --reload-dir open_pulse_sources {{ARGS}}

# ============================================================================
# Testing
# ============================================================================

# Run the full index test suite (parallelized, no live-provider tests)
test:
    .venv/bin/python -m pytest tests/ -q -n auto --dist=loadfile -m 'not live_provider'

# Run specific test file
test-file FILE:
    .venv/bin/python -m pytest {{FILE}} -v

# ============================================================================
# Quality gates
# ============================================================================

# Lint code using ruff
lint:
    uv run ruff check open_pulse_sources/

# Lint and fix issues automatically
lint-fix:
    uv run ruff check --fix open_pulse_sources/

# Type check using mypy
type-check:
    uv run mypy open_pulse_sources/

# Run all code quality checks
check: lint type-check
    @echo "All checks passed!"

# ============================================================================
# Cleanup
# ============================================================================

# Clean up Python cache files
clean-py:
    find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
    find . -type f -name "*.pyc" -delete
    find . -type f -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true

# Clean up test artifacts
clean-test:
    rm -rf .pytest_cache htmlcov .coverage

# Clean up all cache and temporary files
clean-all: clean-py clean-test
# ============================================================================
# Infoscience indexer (open_pulse_sources/index/infoscience)
# ============================================================================

# Solr fulltext discover for configured filter terms.
index-infoscience-discover *ARGS:
    .venv/bin/python -m open_pulse_sources.index.infoscience discover {{ARGS}}

# Download TEXT bundle plaintext for each discovered item.
index-infoscience-fetch-text *ARGS:
    .venv/bin/python -m open_pulse_sources.index.infoscience fetch-text {{ARGS}}

# Regex-extract GitHub/HuggingFace URLs from fetched text.
index-infoscience-extract-matches:
    .venv/bin/python -m open_pulse_sources.index.infoscience extract-matches

# Pull Person/Org authority UUIDs from matched articles.
index-infoscience-extract-relations:
    .venv/bin/python -m open_pulse_sources.index.infoscience extract-relations

# Fetch raw JSON for each linked Person/OrgUnit.
index-infoscience-fetch-related *ARGS:
    .venv/bin/python -m open_pulse_sources.index.infoscience fetch-related {{ARGS}}

# Chunk + embed + populate LanceDB tables.
index-infoscience-embed *ARGS:
    .venv/bin/python -m open_pulse_sources.index.infoscience embed {{ARGS}}

# Hybrid query (filter → vector → rerank). Pass the query as the first arg.
index-infoscience-query QUERY *ARGS:
    .venv/bin/python -m open_pulse_sources.index.infoscience query "{{QUERY}}" {{ARGS}}

# Ingest the on-disk raw/* JSON tree into the infoscience DuckDB store.
# Optional: --links-dump=<path> to merge a dump_link_articles.py output
# into the article_links table.
index-infoscience-ingest-duckdb *ARGS:
    .venv/bin/python -m open_pulse_sources.index.infoscience ingest-duckdb {{ARGS}}

# Show pipeline + LanceDB counts and paths.
index-infoscience-status:
    .venv/bin/python -m open_pulse_sources.index.infoscience status

# ============================================================================
# OpenAlex indexer (open_pulse_sources/index/openalex)
# ============================================================================

# Pull OpenAlex entities into DuckDB. Pass --scope epfl|switzerland.
openalex-ingest *ARGS:
    .venv/bin/python -m open_pulse_sources.index.openalex.cli ingest {{ARGS}}

# Discover Swiss/EPFL Works mentioning github.com URLs (test set for v2).
openalex-find-github *ARGS:
    .venv/bin/python -m open_pulse_sources.index.openalex.cli find-github {{ARGS}}

# Embed DuckDB rows into Qdrant via the RCP embedding endpoint.
openalex-embed *ARGS:
    .venv/bin/python -m open_pulse_sources.index.openalex.cli embed {{ARGS}}

# Re-push existing DuckDB chunks into Qdrant (re-embeds chunks.text via RCP).
# Use after a Qdrant wipe — does NOT modify DuckDB.
openalex-rebuild-qdrant *ARGS:
    .venv/bin/python -m open_pulse_sources.index.openalex.cli rebuild-qdrant {{ARGS}}

# Semantic retrieval (vector + rerank). First positional is the query.
openalex-search QUERY *ARGS:
    .venv/bin/python -m open_pulse_sources.index.openalex.cli search "{{QUERY}}" {{ARGS}}

# Read-only SQL over the DuckDB dump (predefined or guarded ad-hoc).
openalex-query *ARGS:
    .venv/bin/python -m open_pulse_sources.index.openalex.cli query {{ARGS}}

# Run the FastAPI app.
openalex-serve *ARGS:
    .venv/bin/python -m open_pulse_sources.index.openalex.cli serve {{ARGS}}

# Run the OpenAlex test suite only.
openalex-test:
    .venv/bin/python -m pytest tests/index/openalex/ -v -m openalex

# ============================================================================
# ORCID indexer (open_pulse_sources/index/orcid)
# ============================================================================

# Build the seed ORCID list (OpenAlex authors + ORCID expanded-search).
# Pass --scope epfl|switzerland and optionally --source openalex|orcid_search|both.
orcid-discover *ARGS:
    .venv/bin/python -m open_pulse_sources.index.orcid discover {{ARGS}}

# Fetch full ORCID records for seeded IDs, post-filter, persist to DuckDB.
orcid-ingest *ARGS:
    .venv/bin/python -m open_pulse_sources.index.orcid ingest {{ARGS}}

# Chunk + embed in-scope rows, push to Qdrant via the RCP embedding endpoint.
orcid-embed *ARGS:
    .venv/bin/python -m open_pulse_sources.index.orcid embed {{ARGS}}

# Semantic retrieval (vector + RCP rerank). First positional is the query.
orcid-search QUERY *ARGS:
    .venv/bin/python -m open_pulse_sources.index.orcid search "{{QUERY}}" {{ARGS}}

# Read-only SQL over the ORCID DuckDB (predefined or guarded ad-hoc).
orcid-query *ARGS:
    .venv/bin/python -m open_pulse_sources.index.orcid query {{ARGS}}

# Show counts + paths for the chosen scope.
orcid-status *ARGS:
    .venv/bin/python -m open_pulse_sources.index.orcid status {{ARGS}}

# Run the FastAPI app on port 8002 by default.
orcid-serve *ARGS:
    .venv/bin/python -m open_pulse_sources.index.orcid serve {{ARGS}}

# Run the ORCID test suite only.
orcid-test:
    .venv/bin/python -m pytest tests/index/orcid/ -v

# ============================================================================
# HuggingFace indexer (open_pulse_sources/index/huggingface)
# ============================================================================

# Pull HuggingFace metadata + cards into DuckDB. Pass --scope epfl|switzerland
# and optionally --types models,datasets,spaces.
hf-ingest *ARGS:
    .venv/bin/python -m open_pulse_sources.index.huggingface ingest {{ARGS}}

# Substring-search the Hub for unknown EPFL/Swiss orgs; writes candidates to
# logs/discover_orgs.jsonl for human review (never auto-promotes to seed).
hf-discover-orgs *ARGS:
    .venv/bin/python -m open_pulse_sources.index.huggingface discover-orgs {{ARGS}}

# Chunk + embed cards, push vectors to Qdrant via the RCP embedding endpoint.
hf-embed *ARGS:
    .venv/bin/python -m open_pulse_sources.index.huggingface embed {{ARGS}}

# Semantic retrieval (vector + RCP rerank). First positional is the query.
hf-search QUERY *ARGS:
    .venv/bin/python -m open_pulse_sources.index.huggingface search "{{QUERY}}" {{ARGS}}

# Read-only SQL over the HuggingFace DuckDB (predefined or guarded ad-hoc).
hf-query *ARGS:
    .venv/bin/python -m open_pulse_sources.index.huggingface query {{ARGS}}

# Show DuckDB row counts + Qdrant collection size + paths.
hf-status:
    .venv/bin/python -m open_pulse_sources.index.huggingface status

# Run the FastAPI app (default port 8002).
hf-serve *ARGS:
    .venv/bin/python -m open_pulse_sources.index.huggingface serve {{ARGS}}

# Run the HuggingFace test suite only.
hf-test:
    .venv/bin/python -m pytest tests/index/huggingface/ -v

# ============================================================================
# Zenodo indexer (open_pulse_sources/index/zenodo)
# ============================================================================

# Pull Zenodo records into DuckDB. Pass --scope epfl|switzerland.
zenodo-ingest *ARGS:
    .venv/bin/python -m open_pulse_sources.index.zenodo ingest {{ARGS}}

# Chunk + embed records, push vectors to Qdrant via the RCP embedding endpoint.
zenodo-embed *ARGS:
    .venv/bin/python -m open_pulse_sources.index.zenodo embed {{ARGS}}

# Semantic retrieval (vector + RCP rerank). First positional is the query.
zenodo-search QUERY *ARGS:
    .venv/bin/python -m open_pulse_sources.index.zenodo search "{{QUERY}}" {{ARGS}}

# Read-only SQL over the Zenodo DuckDB (predefined or guarded ad-hoc).
zenodo-query *ARGS:
    .venv/bin/python -m open_pulse_sources.index.zenodo query {{ARGS}}

# Show DuckDB row counts + Qdrant collection size + paths.
zenodo-status:
    .venv/bin/python -m open_pulse_sources.index.zenodo status

# Run the FastAPI app (default port 8003).
zenodo-serve *ARGS:
    .venv/bin/python -m open_pulse_sources.index.zenodo serve {{ARGS}}

# ============================================================================
# EPFL Graph disciplines indexer (open_pulse_sources/index/epfl_graph)
# ============================================================================
# RAG index over the curated EPFL Graph academic ontology (~2226 categories,
# 6 levels deep, each backed by 50-110 anchor Wikipedia concepts). Requires
# EPFL_GRAPH_USERNAME / EPFL_GRAPH_PASSWORD for ingest, RCP_TOKEN for embed.

# Walk the ontology tree and persist categories to DuckDB.
epfl-graph-ingest *ARGS:
    .venv/bin/python -m open_pulse_sources.index.epfl_graph ingest {{ARGS}}

# Embed categories and push them into Qdrant collection `epfl_graph_disciplines`.
epfl-graph-embed *ARGS:
    .venv/bin/python -m open_pulse_sources.index.epfl_graph embed {{ARGS}}

# Semantic retrieval over the disciplines index. First positional is the query.
epfl-graph-search QUERY *ARGS:
    .venv/bin/python -m open_pulse_sources.index.epfl_graph search "{{QUERY}}" {{ARGS}}

# DuckDB row counts + Qdrant collection name + paths.
epfl-graph-status:
    .venv/bin/python -m open_pulse_sources.index.epfl_graph status

# ============================================================================
# SWISSUbase indexer (open_pulse_sources/index/swissubase)
# ============================================================================
# SWISSUbase has no public REST API — every catalogue endpoint requires
# the SPA's session cookie. Ingest drives a Selenium browser session and
# calls the JSON endpoints from inside it, so SELENIUM_REMOTE_URL must
# be set. Default scope `epfl_sdsc_ethz` ingests everything but only
# embeds studies whose institution string matches EPFL / ETHZ / SDSC.

# Drive the catalogue via Selenium and persist studies/persons/institutions.
# Pass --scope epfl_sdsc_ethz|switzerland and --limit N for smoke runs.
swissubase-ingest *ARGS:
    .venv/bin/python -m open_pulse_sources.index.swissubase ingest {{ARGS}}

# Chunk + embed in-scope entities, push vectors to Qdrant.
# Pass --entity studies|datasets|persons|institutions to restrict.
swissubase-embed *ARGS:
    .venv/bin/python -m open_pulse_sources.index.swissubase embed {{ARGS}}

# Semantic retrieval (vector + RCP rerank). First positional is the query.
swissubase-search QUERY *ARGS:
    .venv/bin/python -m open_pulse_sources.index.swissubase search "{{QUERY}}" {{ARGS}}

# Read-only SQL over the SWISSUbase DuckDB (predefined or guarded ad-hoc).
swissubase-query *ARGS:
    .venv/bin/python -m open_pulse_sources.index.swissubase query {{ARGS}}

# Show DuckDB row counts + Qdrant collection size + paths.
swissubase-status:
    .venv/bin/python -m open_pulse_sources.index.swissubase status

# Run the FastAPI app (default port 8004).
swissubase-serve *ARGS:
    .venv/bin/python -m open_pulse_sources.index.swissubase serve {{ARGS}}

# ============================================================================
# RenkuLab indexer (open_pulse_sources/index/renkulab)
# ============================================================================

# Pull RenkuLab projects/groups/users/data_connectors into DuckDB.
# Pass --scope all|epfl|switzerland and optionally --only entity1,entity2.
renku-ingest *ARGS:
    .venv/bin/python -m open_pulse_sources.index.renkulab ingest {{ARGS}}

# Chunk + embed entities, push vectors to Qdrant via the RCP embedding endpoint.
# Pass --entities projects,groups,users,data_connectors to restrict (default: all).
renku-embed *ARGS:
    .venv/bin/python -m open_pulse_sources.index.renkulab embed {{ARGS}}

# Semantic retrieval (vector + RCP rerank). First positional is the query.
renku-search QUERY *ARGS:
    .venv/bin/python -m open_pulse_sources.index.renkulab search "{{QUERY}}" {{ARGS}}

# Read-only SQL over the RenkuLab DuckDB (predefined or guarded ad-hoc).
renku-query *ARGS:
    .venv/bin/python -m open_pulse_sources.index.renkulab query {{ARGS}}

# Show DuckDB row counts + Qdrant collection sizes + paths.
renku-status:
    .venv/bin/python -m open_pulse_sources.index.renkulab status

# Run the FastAPI app (default port 8004).
renku-serve *ARGS:
    .venv/bin/python -m open_pulse_sources.index.renkulab serve {{ARGS}}

# ============================================================================
# GitHub repository indexer (open_pulse_sources/index/github)
# ============================================================================

# Fetch GitHub repo metadata + README into DuckDB. Pass --scope epfl|switzerland,
# optionally --repos owner/name,... and/or --from-openalex.
gh-ingest *ARGS:
    .venv/bin/python -m open_pulse_sources.index.github ingest {{ARGS}}

# Chunk + embed repos, push vectors to Qdrant via the RCP embedding endpoint.
gh-embed *ARGS:
    .venv/bin/python -m open_pulse_sources.index.github embed {{ARGS}}

# Recovery path: re-derive Qdrant points from the existing chunks table.
# Use after a Qdrant wipe (instead of `gh-embed`, which would skip everything).
gh-rebuild-qdrant:
    .venv/bin/python -m open_pulse_sources.index.github rebuild-qdrant

# Semantic retrieval (vector + RCP rerank). First positional is the query.
gh-search QUERY *ARGS:
    .venv/bin/python -m open_pulse_sources.index.github search "{{QUERY}}" {{ARGS}}

# Read-only SQL over the GitHub DuckDB (predefined or guarded ad-hoc).
gh-query *ARGS:
    .venv/bin/python -m open_pulse_sources.index.github query {{ARGS}}

# Show DuckDB row counts + Qdrant collection size + paths.
gh-status:
    .venv/bin/python -m open_pulse_sources.index.github status

# Run the FastAPI app (default port 8004).
gh-serve *ARGS:
    .venv/bin/python -m open_pulse_sources.index.github serve {{ARGS}}

# ============================================================================
# Federated cross-index layer (open_pulse_sources/index/_federated)
# ============================================================================

# Federated semantic search across every registered index in parallel.
# Pass `--indices huggingface,openalex` to scope; `--filter k=v` (repeatable);
# `--entity-type X` to restrict each adapter to one type.
gme-search QUERY *ARGS:
    .venv/bin/python -m open_pulse_sources.index._federated search "{{QUERY}}" {{ARGS}}

# Cross-index entity lookup. Pass any identifier — slug, URL, ORCID, ROR,
# DOI, UUID — and every adapter that recognises it returns matches.
gme-entity ID *ARGS:
    .venv/bin/python -m open_pulse_sources.index._federated entity "{{ID}}" {{ARGS}}

# List registered adapters and the entity types each exposes.
gme-indices:
    .venv/bin/python -m open_pulse_sources.index._federated indices

# Walk the HF base_models DAG (ancestors + descendants) from a repo_id.
hf-lineage REPO_ID *ARGS:
    .venv/bin/python -m open_pulse_sources.index.huggingface lineage "{{REPO_ID}}" {{ARGS}}

# ============================================================================
# Docker
# ============================================================================

# Build the service image
docker-build:
    docker build -t open-pulse-sources -f tools/image/Dockerfile .

# Run the service container (expects .env with API_TOKEN, RCP_TOKEN, …)
docker-run:
    docker run -it --rm --env-file .env -p 8080:8080 --name open-pulse-sources open-pulse-sources

# Bring up the standalone stack (service + qdrant + selenium)
compose-up:
    docker compose -f tools/deploy/docker-compose.yml --env-file .env up -d

# Tear down the standalone stack
compose-down:
    docker compose -f tools/deploy/docker-compose.yml down
