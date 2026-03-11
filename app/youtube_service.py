from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import parse_qs
from urllib.parse import urlparse

import requests
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.proxies import GenericProxyConfig


RETRYABLE_ERROR_NAMES: set[str] = {
    "RequestBlocked",
    "IpBlocked",
    "YouTubeRequestFailed",
}


@dataclass(frozen=True)
class TranscriptRequest:
    video_id: str
    languages: list[str]
    preserve_formatting: bool
    prefer_generated: bool
    format: str


def extract_video_id(url: str) -> str:
    parsed = urlparse(url)
    host: str = parsed.netloc.lower()
    if host in {"youtu.be", "www.youtu.be"}:
        video_id: str = parsed.path.strip("/")
        if not video_id:
            raise ValueError("missing video id in short youtube url")
        return video_id

    if host in {"youtube.com", "www.youtube.com", "m.youtube.com"}:
        if parsed.path == "/watch":
            query: dict[str, list[str]] = parse_qs(parsed.query)
            values: list[str] = query.get("v", [])
            if values and values[0].strip():
                return values[0].strip()
        if parsed.path.startswith("/shorts/"):
            video_id = parsed.path.removeprefix("/shorts/").strip("/")
            if video_id:
                return video_id

    raise ValueError("unsupported youtube url")


def _build_api(proxy_url: str | None, user_agent: str) -> YouTubeTranscriptApi:
    session: requests.Session = requests.Session()
    session.headers.update({"User-Agent": user_agent})
    if proxy_url is None:
        return YouTubeTranscriptApi(http_client=session)

    return YouTubeTranscriptApi(
        proxy_config=GenericProxyConfig(http_url=proxy_url, https_url=proxy_url),
        http_client=session,
    )


def fetch_transcript(
    request: TranscriptRequest,
    proxy_url: str | None,
    user_agent: str,
) -> dict[str, object]:
    api: YouTubeTranscriptApi = _build_api(proxy_url=proxy_url, user_agent=user_agent)

    if request.prefer_generated:
        transcript = api.list(request.video_id).find_generated_transcript(
            request.languages
        )
        fetched = transcript.fetch(preserve_formatting=request.preserve_formatting)
    else:
        fetched = api.fetch(
            request.video_id,
            languages=request.languages,
            preserve_formatting=request.preserve_formatting,
        )

    snippets: list[dict[str, object]] = [
        {
            "text": snippet.text,
            "start": snippet.start,
            "duration": snippet.duration,
        }
        for snippet in fetched
    ]

    response: dict[str, object] = {
        "video_id": fetched.video_id,
        "language": fetched.language,
        "language_code": fetched.language_code,
        "is_generated": fetched.is_generated,
        "snippets": snippets,
    }
    if request.format == "text":
        transcript_lines: list[str] = [str(snippet["text"]) for snippet in snippets]
        response["transcript"] = "\n".join(transcript_lines)
    return response


def is_retryable_exception(err: Exception) -> bool:
    return type(err).__name__ in RETRYABLE_ERROR_NAMES
