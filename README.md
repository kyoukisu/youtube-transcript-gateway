# youtube-transcript-gateway

Small FastAPI service for fetching YouTube transcripts with:

- proxy rotation (round-robin)
- proxy cooldown on block/network failures
- optional direct fallback
- bearer auth for inbound requests
- in-memory TTL cache

## Endpoints

- `GET /healthz`
- `GET /transcript?url=...`
- `GET /transcript?video_id=...`

## Request examples

```bash
curl "http://127.0.0.1:8091/transcript?url=https://www.youtube.com/watch?v=dQw4w9WgXcQ"
curl "http://127.0.0.1:8091/transcript?video_id=dQw4w9WgXcQ&languages=en,ru&format=json"
```

If `INBOUND_API_TOKEN` is set:

```bash
curl -H "Authorization: Bearer your_token" \
  "http://127.0.0.1:8091/transcript?video_id=dQw4w9WgXcQ"
```

## Query params

- `url` or `video_id` (exactly one required)
- `languages=ru,en` optional
- `format=text|json` default `text`
- `preserve_formatting=true|false` default `false`
- `prefer_generated=true|false` default `false`

## Response behavior

- `200` transcript returned
- `400` invalid params
- `401` unauthorized
- `404` transcript unavailable / not found
- `429` all proxies cooling down and direct fallback disabled
- `503` retries exhausted or upstream transport failures

Debug headers:

- `X-Cache`
- `X-Proxy-Index`
- `X-Rotator-Failed`

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8091
```

## Run in Docker

```bash
cp .env.example .env
docker compose up --build -d
```

## Dokploy notes

- This compose expects the external network `dokploy-network` to exist.
- For Dokploy deploys, keep runtime secrets in compose env, not in git.
- Suggested public domain: `youtube-transcript.beako.best`.
