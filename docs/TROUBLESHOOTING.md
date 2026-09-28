# Troubleshooting

## `RedisCache` tests skip with "local Redis not reachable"

Start Redis first: `docker compose up -d redis`. The fixture in
`tests/test_cache.py` calls `pytest.skip(...)` rather than failing when
`redis://localhost:6379` isn't reachable, so the rest of the suite still
runs — check `docker ps` for a `genai-gateway-redis-1` container if the
skip is unexpected.

## `429 Too Many Requests` during manual testing

`RATE_LIMIT_CAPACITY` (default 20) and `RATE_LIMIT_REFILL_PER_SECOND`
(default 1) are env vars on `genai_gateway/app.py`. If you're hammering
`/generate` with the same `client_id` faster than the refill rate, this
is the rate limiter working as designed, not a bug. Use a different
`client_id` per test session or raise the env vars for local load testing.

## A prompt I expect to hit the model instead returns `decision_source: "retrieval"`

Check `genai_gateway/retrieval/knowledge_base.py::KNOWLEDGE_BASE` — the
weak-keyword matching is substring-based (`kw in lowered`), so a keyword
like `"rollout"` matches any prompt containing that substring, including
unrelated ones ("we need a rollout plan for the marketing campaign" would
still enrich against the k8s_rollback entry). This is a known false-positive
mode of simple substring matching, not a bug specific to one prompt — a
real system would want word-boundary matching or actual embeddings here.

## `python3 -m venv` picks Python 3.14 and `redis`/`prometheus_client` fail to build

Same root cause as documented in the sibling `release-risk-ml` repo's
troubleshooting doc: use `python3.12` explicitly for the venv. This
repo's dependencies (`redis`, `prometheus_client`, `fastapi`) have
prebuilt wheels for 3.12; 3.14 wheel coverage was incomplete on the
machine this was built on.

## `docker compose up -d redis` hangs or fails

Check `docker info` first — the daemon itself may not be running yet even
though the `docker` CLI is installed (`open -a Docker` on macOS, then wait
for the daemon before retrying `docker compose up`).
