"""Shared setup for the index-service test suite.

Env defaults must land before test modules import ``open_pulse_sources.service.api`` /
``open_pulse_sources.index.*`` — some index config modules read tokens at import time,
and the auth dependency fails closed without ``API_TOKEN``.
"""
from __future__ import annotations

import os

os.environ.setdefault("GME_GITHUB_TOKEN", "ci-test-github-token")
os.environ.setdefault("API_TOKEN", "ci-test-api-token")

import pytest


@pytest.fixture(autouse=True)
def _isolate_service_runtime_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default bearer token for `verify_token` — mirrors the monolith's
    `_isolate_v2_runtime_env` fixture that these ported tests were written
    against. Individual tests override/delete to exercise auth paths."""
    monkeypatch.setenv("API_TOKEN", "test-api-token")
