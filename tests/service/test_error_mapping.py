"""Missing-credential errors must surface as 503, not raw 500s.

Found in the 2026-07-14 live smoke tests (GME task brief 04): search routes
let ``require_rcp()``'s ``ValueError`` escape as an unhandled 500. The app
now maps the "Missing required environment variable" family to 503.
"""
from __future__ import annotations

import asyncio
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

TEST_API_TOKEN = "test-api-token"  # noqa: S105 — test fixture
_AUTH_HEADERS = {"Authorization": f"Bearer {TEST_API_TOKEN}"}


def _request(method: str, path: str, **kwargs: Any) -> tuple[int, Any]:
    # Import inside so the autouse env fixture applies before app import.
    from open_pulse_sources.service.app import app

    async def _run() -> tuple[int, Any]:
        transport = ASGITransport(app=app, raise_app_exceptions=False)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.request(method, path, headers=_AUTH_HEADERS, **kwargs)
        try:
            body: Any = resp.json()
        except Exception:  # noqa: BLE001
            body = resp.text
        return resp.status_code, body

    return asyncio.run(_run())


def test_search_without_rcp_token_returns_503(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("RCP_TOKEN", raising=False)
    status, body = _request(
        "POST", "/v2/indices/zenodo_records/search", json={"query": "anything"},
    )
    assert status == 503, body
    assert "RCP_TOKEN" in str(body.get("detail", ""))


def test_other_value_errors_keep_500_shape() -> None:
    from open_pulse_sources.service.app import missing_env_error_handler

    resp = asyncio.run(missing_env_error_handler(None, ValueError("boom")))
    assert resp.status_code == 500
