"""Local gateway service. Run with:

    uvicorn genai_gateway.app:app --port 8000

Uses MockProvider by default (no API key, no network calls) and an
in-memory cache unless REDIS_URL is set and reachable.
"""

import os

from fastapi import FastAPI, HTTPException, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from genai_gateway.cache.cache_backend import get_cache_backend
from genai_gateway.gateway import GenAIGateway, RateLimitExceeded
from genai_gateway.providers.mock_provider import MockProvider
from genai_gateway.rate_limit.token_bucket import TokenBucketLimiter
from genai_gateway.schemas import GatewayRequest, GatewayResponse

RATE_LIMIT_CAPACITY = int(os.environ.get("RATE_LIMIT_CAPACITY", "20"))
RATE_LIMIT_REFILL_PER_SECOND = float(os.environ.get("RATE_LIMIT_REFILL_PER_SECOND", "1"))
CACHE_TTL_SECONDS = int(os.environ.get("CACHE_TTL_SECONDS", "300"))

app = FastAPI(title="genai-gateway")

_gateway = GenAIGateway(
    provider=MockProvider(),
    cache=get_cache_backend(os.environ.get("REDIS_URL")),
    rate_limiter=TokenBucketLimiter(RATE_LIMIT_CAPACITY, RATE_LIMIT_REFILL_PER_SECOND),
    cache_ttl_seconds=CACHE_TTL_SECONDS,
)


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok"}


@app.get("/metrics")
def metrics_endpoint() -> Response:
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post("/generate", response_model=GatewayResponse)
def generate(request: GatewayRequest) -> GatewayResponse:
    try:
        return _gateway.handle(request)
    except RateLimitExceeded as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
