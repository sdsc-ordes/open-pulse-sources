"""Text-related EPFL Graph endpoints.

Wraps `graphai_client.client_api.translation`, `text` and `embedding`.
Each wrapper auto-resolves `login_info` from env vars when not supplied.
"""

from __future__ import annotations

from typing import Any

from graphai_client.client_api import embedding as _embedding
from graphai_client.client_api import text as _text
from graphai_client.client_api import translation as _translation

from open_pulse_sources.module.epfl_graph.auth import get_login_info


def detect_language(
    text: str | list[str | None],
    login_info: dict | None = None,
    **kwargs: Any,
) -> str | list[str | None] | None:
    return _translation.detect_language(
        text=text, login_info=login_info or get_login_info(), **kwargs,
    )


def translate_text(
    text: str | list[str | None],
    source_language: str,
    target_language: str,
    login_info: dict | None = None,
    **kwargs: Any,
) -> str | list[str | None] | None:
    return _translation.translate_text(
        text=text,
        source_language=source_language,
        target_language=target_language,
        login_info=login_info or get_login_info(),
        **kwargs,
    )


def extract_concepts_from_text(
    text: str,
    login_info: dict | None = None,
    **kwargs: Any,
) -> list[dict] | None:
    return _text.extract_concepts_from_text(
        text=text, login_info=login_info or get_login_info(), **kwargs,
    )


def extract_keywords_from_text(
    text: str,
    login_info: dict | None = None,
    **kwargs: Any,
) -> list[str] | None:
    return _text.extract_keywords_from_text(
        text=text, login_info=login_info or get_login_info(), **kwargs,
    )


def extract_concepts_from_keywords(
    keywords: list[str],
    login_info: dict | None = None,
    **kwargs: Any,
) -> list[dict] | None:
    return _text.extract_concepts_from_keywords(
        keywords=keywords, login_info=login_info or get_login_info(), **kwargs,
    )


def embed_text(
    text: str | list[str | None],
    login_info: dict | None = None,
    **kwargs: Any,
):
    return _embedding.embed_text(
        text=text, login_info=login_info or get_login_info(), **kwargs,
    )
