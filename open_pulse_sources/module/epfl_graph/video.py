"""Video-related EPFL Graph endpoints.

Wraps `graphai_client.client_api.video` for video token retrieval,
fingerprinting, audio extraction, slide extraction and resource downloads.
"""

from __future__ import annotations

from typing import Any

from graphai_client.client_api import video as _video

from open_pulse_sources.module.epfl_graph.auth import get_login_info


def get_video_token(
    url_video: str,
    login_info: dict | None = None,
    **kwargs: Any,
) -> tuple[str | None, int | None, list | None]:
    return _video.get_video_token(
        url_video=url_video, login_info=login_info or get_login_info(), **kwargs,
    )


def fingerprint_video(
    video_token: str,
    login_info: dict | None = None,
    **kwargs: Any,
) -> str | None:
    return _video.fingerprint_video(
        video_token=video_token, login_info=login_info or get_login_info(), **kwargs,
    )


def extract_audio(
    video_token: str,
    login_info: dict | None = None,
    **kwargs: Any,
) -> str | None:
    return _video.extract_audio(
        video_token=video_token, login_info=login_info or get_login_info(), **kwargs,
    )


def extract_slides(
    video_token: str,
    login_info: dict | None = None,
    **kwargs: Any,
) -> dict | None:
    return _video.extract_slides(
        video_token=video_token, login_info=login_info or get_login_info(), **kwargs,
    )


def download_file(
    token: str,
    file_path: str,
    login_info: dict | None = None,
    **kwargs: Any,
) -> str | None:
    return _video.download_file(
        token=token,
        file_path=file_path,
        login_info=login_info or get_login_info(),
        **kwargs,
    )
