from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from fastapi import FastAPI
from fastapi import Query
from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.responses import Response

from app.cache import TtlCache
from app.config import Settings
from app.config import load_settings
from app.pools import RoundRobinPool
from app.youtube_service import TranscriptRequest
from app.youtube_service import extract_video_id
from app.youtube_service import fetch_transcript
from app.youtube_service import is_retryable_exception


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger: logging.Logger = logging.getLogger("youtube-transcript-gateway")


settings: Settings = load_settings()
proxy_pool: RoundRobinPool | None = (
    RoundRobinPool("proxies", settings.proxies) if settings.proxies else None
)
cache: TtlCache = TtlCache(
    ttl_seconds=settings.cache_ttl_seconds,
    max_items=settings.cache_max_items,
)

app: FastAPI = FastAPI(title="youtube-transcript-gateway", version="0.1.0")


@dataclass
class AttemptLog:
    proxy_index: int | None
    route: str
    outcome: str
    error: str | None


def _check_auth(request: Request) -> bool:
    if settings.api_token is None:
        return True
    auth_header: str | None = request.headers.get("authorization")
    expected: str = f"Bearer {settings.api_token}"
    return auth_header == expected


def _response_headers(
    proxy_index: int | None,
    failed_after_retries: bool,
    cache_hit: bool,
) -> dict[str, str]:
    headers: dict[str, str] = {
        "X-Cache": "hit" if cache_hit else "miss",
    }
    if proxy_index is not None:
        headers["X-Proxy-Index"] = str(proxy_index)
    if failed_after_retries:
        headers["X-Rotator-Failed"] = "true"
    return headers


def _cache_key(req: TranscriptRequest) -> str:
    return "|".join(
        [
            req.video_id,
            ",".join(req.languages),
            req.format,
            str(req.preserve_formatting),
            str(req.prefer_generated),
        ]
    )


@app.get("/healthz")
def healthz() -> dict[str, object]:
    return {
        "ok": True,
        "proxies": proxy_pool.summary() if proxy_pool else None,
        "cache": cache.summary(),
        "proxy_fallback_to_direct": settings.proxy_fallback_to_direct,
    }


@app.get("/transcript")
def transcript(
    request: Request,
    url: str | None = None,
    video_id: str | None = None,
    languages: str | None = None,
    preserve_formatting: bool = False,
    prefer_generated: bool = False,
    format: str = Query(default="text", pattern="^(text|json)$"),
) -> Response:
    if not _check_auth(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    if bool(url) == bool(video_id):
        return JSONResponse(
            {"error": "provide exactly one of: url or video_id"},
            status_code=400,
        )

    resolved_video_id: str
    try:
        resolved_video_id = (
            video_id.strip() if video_id else extract_video_id(url or "")
        )
    except ValueError as err:
        return JSONResponse({"error": str(err)}, status_code=400)

    requested_languages: list[str] = (
        [item.strip() for item in languages.split(",") if item.strip()]
        if languages
        else settings.languages_default
    )
    if not requested_languages:
        return JSONResponse({"error": "languages must not be empty"}, status_code=400)

    transcript_request: TranscriptRequest = TranscriptRequest(
        video_id=resolved_video_id,
        languages=requested_languages,
        preserve_formatting=preserve_formatting,
        prefer_generated=prefer_generated,
        format=format,
    )

    cache_key: str = _cache_key(transcript_request)
    cached: dict[str, object] | None = cache.get(cache_key)
    if cached is not None:
        return JSONResponse(cached, headers=_response_headers(None, False, True))

    attempts: list[AttemptLog] = []
    max_attempts: int = max(settings.max_attempts, 1)
    last_proxy_index: int | None = None

    for _ in range(max_attempts):
        proxy_index: int | None = None
        proxy_url: str | None = None
        route: str = "direct"

        if proxy_pool is not None:
            proxy_pick: tuple[int, str] | None = proxy_pool.acquire()
            if proxy_pick is not None:
                proxy_index, proxy_url = proxy_pick
                proxy_pool.reserve(proxy_index, settings.proxy_min_interval_seconds)
                route = f"proxy:{proxy_index}"
            else:
                wait_seconds: float | None = proxy_pool.next_available_in()
                if (
                    wait_seconds is not None
                    and wait_seconds > 0
                    and wait_seconds <= settings.proxy_wait_for_slot_seconds
                ):
                    time.sleep(wait_seconds)
                    continue
                if not settings.proxy_fallback_to_direct:
                    return JSONResponse(
                        {
                            "error": "all proxies are cooling down",
                            "attempts": [a.__dict__ for a in attempts],
                        },
                        status_code=429,
                    )
                route = "direct-fallback"

        try:
            payload: dict[str, object] = fetch_transcript(
                request=transcript_request,
                proxy_url=proxy_url,
                user_agent=settings.user_agent,
            )
            if proxy_pool is not None and proxy_index is not None:
                proxy_pool.mark_success(proxy_index)
            cache.set(cache_key, payload)
            return JSONResponse(
                payload,
                headers=_response_headers(proxy_index, False, False),
            )
        except Exception as err:
            error_name: str = type(err).__name__
            last_proxy_index = proxy_index
            retryable: bool = is_retryable_exception(err)
            if proxy_pool is not None and proxy_index is not None:
                if retryable:
                    proxy_pool.mark_failure(
                        proxy_index,
                        settings.proxy_cooldown_seconds,
                        error_name,
                    )
                else:
                    proxy_pool.mark_success(proxy_index)

            attempts.append(
                AttemptLog(
                    proxy_index=proxy_index,
                    route=route,
                    outcome="retryable_error" if retryable else "terminal_error",
                    error=error_name,
                )
            )

            if not retryable:
                lowered: str = str(err).lower()
                status_code: int = 404
                if "transcript" not in lowered and "subtitles" not in lowered:
                    status_code = 503
                return JSONResponse(
                    {
                        "error": str(err),
                        "error_type": error_name,
                        "attempts": [a.__dict__ for a in attempts],
                    },
                    status_code=status_code,
                    headers=_response_headers(proxy_index, False, False),
                )

    return JSONResponse(
        {
            "error": "retries exhausted",
            "attempts": [a.__dict__ for a in attempts],
        },
        status_code=503,
        headers=_response_headers(last_proxy_index, True, False),
    )
