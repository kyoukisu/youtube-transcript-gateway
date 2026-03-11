from __future__ import annotations

import os
from dataclasses import dataclass


def _as_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    normalized: str = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def _as_float(value: str | None, default: float) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _as_int(value: str | None, default: int) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _as_csv(value: str | None) -> list[str]:
    if value is None:
        return []
    parts: list[str] = [x.strip() for x in value.split(",")]
    return [x for x in parts if x]


@dataclass(frozen=True)
class Settings:
    host: str
    port: int
    api_token: str | None
    request_timeout_seconds: float
    max_attempts: int
    user_agent: str
    languages_default: list[str]
    proxies: list[str]
    proxy_fallback_to_direct: bool
    proxy_cooldown_seconds: float
    proxy_min_interval_seconds: float
    proxy_wait_for_slot_seconds: float
    cache_ttl_seconds: int
    cache_max_items: int


def load_settings() -> Settings:
    host: str = os.getenv("HOST", "0.0.0.0")
    port: int = _as_int(os.getenv("PORT"), 8091)
    api_token_raw: str | None = os.getenv("INBOUND_API_TOKEN")
    api_token: str | None = api_token_raw.strip() if api_token_raw else None
    proxies: list[str] = _as_csv(os.getenv("PROXIES"))

    return Settings(
        host=host,
        port=port,
        api_token=api_token,
        request_timeout_seconds=_as_float(os.getenv("REQUEST_TIMEOUT_SECONDS"), 45.0),
        max_attempts=_as_int(os.getenv("MAX_ATTEMPTS"), 8),
        user_agent=os.getenv(
            "USER_AGENT", "youtube-transcript-gateway/0.1 (+https://github.com/)"
        ),
        languages_default=_as_csv(os.getenv("LANGUAGES_DEFAULT")) or ["en"],
        proxies=proxies,
        proxy_fallback_to_direct=_as_bool(os.getenv("PROXY_FALLBACK_TO_DIRECT"), True),
        proxy_cooldown_seconds=_as_float(os.getenv("PROXY_COOLDOWN_SECONDS"), 60.0),
        proxy_min_interval_seconds=_as_float(
            os.getenv("PROXY_MIN_INTERVAL_SECONDS"), 0.0
        ),
        proxy_wait_for_slot_seconds=_as_float(
            os.getenv("PROXY_WAIT_FOR_SLOT_SECONDS"), 2.0
        ),
        cache_ttl_seconds=_as_int(os.getenv("CACHE_TTL_SECONDS"), 21600),
        cache_max_items=_as_int(os.getenv("CACHE_MAX_ITEMS"), 1000),
    )
