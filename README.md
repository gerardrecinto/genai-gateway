# genai-gateway

A provider-agnostic GenAI gateway: deterministic policy checks and
structured retrieval run first, a model call happens only when neither
resolves the request, and every path is cached, rate-limited, traced, and
audit-logged without storing raw prompt/response content.

**Honesty note**: I have no prior professional experience operating
production GenAI infrastructure at this scope. This is an independently
built portfolio project demonstrating the pattern hands-on — validation,
retrieval-before-model, caching, rate limiting, response validation and
escalation, tracing, audit logging — using a local mock model provider so
none of it depends on a paid API. My real production GenAI work
(`devops-mcp`, `ci-triage`) uses the same rules-first philosophy (RAIL:
Rules Applied Instantly, LLM only for what's left) at smaller scope; this
project generalizes that pattern into a standalone gateway.

## Request path

```
POST /generate
      |
      v
pydantic validation (schemas.GatewayRequest)  -- 422 on malformed input
      |
      v
rate limiter (per-client token bucket)         -- 429 if exceeded
      |
      v
policy layer (policy/rules.py)                 -- deterministic, <1ms
      |  blocked?  --yes--> return policy_block, no cache write, no model call
      v no
retrieval (retrieval/knowledge_base.py)
      |  strong match --> cache + return "retrieval", no model call
      |  weak match    --> attach as context, continue
      v no match
cache lookup (cache/cache_backend.py, Redis or in-memory)
      |  hit --> return "cache", no model call
      v miss
model call (providers/mock_provider.py or a real ModelProvider)
      |  exception --> return "fallback", provider_error
      v
response validation (gateway.py::validate_response)
      |  fails --> return "fallback", response_validation_failed
      v passes
confidence heuristic (gateway.py::assess_confidence)
      |
      v
cache write, metrics, audit log, return "model"
```

Every branch — including the blocked and fallback ones — goes through the
same audit-logging and metrics path (`GenAIGateway._finish`), so nothing
exits the pipeline unaccounted for.

## Local quickstart

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip install -e .

# optional: real Redis instead of the in-memory cache fallback
docker compose up -d redis

uvicorn genai_gateway.app:app --port 8000
# in another shell:
scripts/smoke_test.sh http://localhost:8000
```

No API key is required — the default provider is `MockProvider`
(`genai_gateway/providers/mock_provider.py`), a deterministic local
stand-in with no network calls.

Run tests (redis-backed cache tests auto-skip if `docker compose up -d
redis` hasn't been run):

```bash
python -m pytest tests/ -v
```

**Observed**: 30/30 tests passing in this repo, including live
integration tests against a real local Redis instance (not mocked) — see
`tests/test_cache.py::test_redis_cache_set_and_get` and related.

## Why retrieval-before-model, not RAG

`retrieval/knowledge_base.py` is a small hand-authored dict of runbook
snippets, not a vector store — deliberately. The point being demonstrated
is the *decision*: does this request need a model call at all, or does a
known-answer lookup resolve it deterministically? A `strong_phrases` match
answers directly and skips the model entirely (same pattern as the RAIL
rule gate in the sibling `release-risk-ml` project); a `weak_keywords`
match only enriches context for the model, since a loose keyword overlap
isn't confident enough to answer without one. A real system would likely
combine this with actual vector retrieval for the enrich path — not built
here, noted as the natural next slice.

## Confidence and escalation

`assess_confidence()` is a hedging-phrase heuristic ("I'm not sure", "it
depends", etc.) — genuinely simple, not a calibrated confidence score.
A response that trips it sets `needs_human_review: true` in the response.
This is intentionally conservative: false positives (flagging a
confident answer as uncertain) cost a human a few seconds of review;
false negatives (missing genuine uncertainty) cost a wrong answer going
out unflagged. The heuristic is tuned to fail toward the cheaper mistake.

## Provider-agnostic design

`providers/base.py` defines a `ModelProvider` protocol (`generate(prompt,
context) -> ProviderResponse`). `MockProvider` implements it with no
dependencies. `providers/anthropic_provider.py` implements the same
interface against the real Anthropic API — **it has not been exercised
in this project's test suite or CI, and no API key is configured here**;
it exists to show the adapter shape, not a verified integration. Swapping
providers in `app.py` is a one-line change (`provider=MockProvider()` ->
`provider=AnthropicProvider()`); nothing else in the gateway (policy,
retrieval, cache, rate limiting, validation, audit) depends on which
provider is active.

## Repo layout

```
genai_gateway/
  schemas.py              request/response pydantic contracts
  policy/rules.py          deterministic policy checks (secret exfil, prompt injection, PII flagging)
  retrieval/knowledge_base.py   structured context lookup, resolve vs enrich
  cache/cache_backend.py    InMemoryCache + RedisCache behind one interface
  rate_limit/token_bucket.py per-client token bucket limiter
  providers/
    base.py                ModelProvider protocol
    mock_provider.py        deterministic local provider (used by default)
    anthropic_provider.py   real-provider adapter shape, unexercised
  tracing.py                request id + per-stage latency
  audit.py                  structured audit log, hash-only, no raw content
  metrics.py                Prometheus counters/histograms
  gateway.py                orchestrates the full pipeline
  app.py                    FastAPI service
docker-compose.yml          local Redis for the optional cache backend
tests/                       30 unit + integration tests (pytest), Redis tests live
scripts/smoke_test.sh        black-box smoke test against a running instance
docs/                         architecture, security, cost, troubleshooting, portfolio summary
```
