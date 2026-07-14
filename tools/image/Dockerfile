FROM ghcr.io/astral-sh/uv:python3.12-bookworm

ENV LC_ALL=C.UTF-8
ENV LANG=C.UTF-8

RUN useradd -ms /bin/bash -u 1000 non-root-user

WORKDIR /app
COPY open_pulse_sources ./open_pulse_sources
# Deployment parameters: per-index yaml (config/index/) + seed identifier
# lists (config/seeds/, override with SEEDS_DIR). load_config() resolves
# yaml CWD-relative; deploy-specific values (Qdrant URL, tokens, scope)
# stay env-overridable.
COPY config ./config
# Operational scripts (reingest_indices.py, migrate_monolith_to_split.py, …).
COPY scripts ./scripts
COPY pyproject.toml README.md ./

RUN uv pip install --system .

# data/ holds the per-index DuckDB stores + provider cache. In compose this
# is a volume shared with the extraction service (gme-api), which reads the
# same stores.
RUN mkdir -p /app/data /app/.cache && chown -R non-root-user:non-root-user /app

USER non-root-user

ENV PYTHONPATH=/app
ENV WORKERS=1

EXPOSE 8080

# The index management API: /v2/manifest + /v2/indices/* (ingest / search /
# stats / compact / reset). /health is open; everything else needs API_TOKEN.
ENTRYPOINT ["sh", "-c", "uvicorn open_pulse_sources.service.app:app --host 0.0.0.0 --port 8080 --workers ${WORKERS}"]
