# genai-gateway

A local GenAI gateway for engineers testing policy and retrieval before a model call. It includes a mock provider, optional Redis caching, process-local rate limiting, timing, and audit records without raw prompt or response text.

**Scope:** I built this independently as a portfolio project. I have no prior professional experience operating production GenAI infrastructure at this scope. The default provider is a local mock, so the checked-in path needs no paid API.

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
policy layer (policy/rules.py)                 -- deterministic
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

Completed generation decisions, including policy blocks and provider fallbacks, use the same audit and metrics path (`GenAIGateway._finish`). Schema rejections (422) and rate-limit rejections (429) are separate HTTP error paths. A cache outage does not discard a valid answer.

## Local quickstart

```bash
git clone https://github.com/gerardrecinto/genai-gateway.git
cd genai-gateway
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
uvicorn genai_gateway.app:app --port 8000
```

In another terminal, start from the clone's parent directory and run:

```bash
cd genai-gateway
scripts/smoke_test.sh http://localhost:8000
```

The default cache is in memory. To use local Redis, stop the API, then run:

```bash
docker compose up -d --wait redis
REDIS_URL=redis://127.0.0.1:6379 uvicorn genai_gateway.app:app --port 8000
```

Docker is optional. Redis is bound to loopback for this local demo. The service has no authentication, and the caller supplies `client_id`; the rate limiter is a fairness mechanism, not a security boundary.

No API key is required — the default provider is `MockProvider`
(`genai_gateway/providers/mock_provider.py`), a deterministic local
stand-in with no network calls.

Run tests (redis-backed cache tests auto-skip if `docker compose up -d
redis` hasn't been run):

```bash
python -m pytest tests/ -v
```

CI runs the tests with a real Redis service and fails if that service is unavailable. Without local Redis, the three integration tests skip with an explanation. CI also checks package installation, the HTTP smoke flow, audit output, lint, and dependency advisories.

The request's `context` mapping is reserved. It is not forwarded to the provider or included in cache keys.

## Sensitive-data handling

Added so the gateway can sit in front of prompts that contain identifiers, with controls that are tested and enforced in CI. **All test data is synthetic. This is an engineering control mapping from a portfolio project. It is not a HIPAA, FDA or any other compliance claim, and I have not shipped software under those regimes.**

| Control | Where | What it does |
|---|---|---|
| Detect and redact | `sensitive.py`, `policy/rules.py` | SSN, card number, email, phone, medical record number and labeled date of birth become `[SSN]`, `[EMAIL]` and so on before retrieval, the cache key or the model sees the prompt |
| Per-client policy | `classification.py` | `allow`, `redact` (default) or `block` per `client_id`, set with `GATEWAY_DATA_POLICY`. Block returns `sensitive_data_blocked` and never calls the model |
| Log redaction | `sensitive.py` | A log record factory redacts every message in the process, not only the audit logger |
| Tamper-evident audit chain | `audit_chain.py` | One JSON line per request, each hash covers the previous hash, so edits, deletions and reordering break verification |
| Encrypted payloads | `audit_chain.py` | Payloads (record plus the redacted prompt) are encrypted with Fernet from the `cryptography` package; key in `GATEWAY_AUDIT_KEY` |
| Controls as CI checks | `scripts/controls_check.sh`, `controls` job | Fails the build if redaction tests, the end-to-end tamper check or the secrets scan fail |

Turn on the chain:

```bash
export GATEWAY_AUDIT_KEY=$(python -m genai_gateway.audit_chain keygen)
export GATEWAY_AUDIT_CHAIN_PATH=./audit.jsonl
export GATEWAY_DATA_POLICY='{"default":"redact","clients":{"clinic-app":"block"}}'
uvicorn genai_gateway.app:app --port 8000

python -m genai_gateway.audit_chain verify ./audit.jsonl --key-env GATEWAY_AUDIT_KEY
python -m genai_gateway.audit_chain head ./audit.jsonl   # store this value somewhere else
```

### Control mapping (engineering view only)

| Engineering control | Intent it supports |
|---|---|
| Redact before model call, per-client block | Minimum necessary data leaves the boundary |
| Hash-chained, encrypted audit log with a verifier | Records of access that show if they were altered |
| Fail closed on audit write errors | No answer returned without an audit entry |
| Secrets scan and redaction tests gating the build | Controls cannot be dropped silently in a change |

### What it does not do

- Pattern matching finds identifiers that look like identifiers. It does not find free-text names, street addresses or diagnoses. A real deployment needs a trained detector on top, and a decision about what counts as sensitive.
- The chain proves internal consistency. Someone who can rewrite the whole file can recompute the hashes. Verifying with the key catches forged payloads, and storing the `head` hash elsewhere (`--expect-head`) catches truncation and full rewrites. Tests cover each of these cases, including the one that passes without the key and fails with it.
- Fernet uses one shared key, with no rotation or KMS here. The key sits in an environment variable.
- Fail closed means an unwritable audit file returns a 500 even though the model already ran. I chose auditability over availability; flip that if uptime matters more.
- The provider is still the mock. Nothing here was run against a real model or real patient data.

### Bugs found while building it

- The audit `prompt_hash` was a hash of the raw prompt. A low-entropy identifier such as an SSN could be recovered by hashing guesses against the log. It now hashes the redacted prompt (regression test `test_prompt_hash_ignores_the_identifier_value`).
- In redact mode the audit record reported no redacted types, because the prompt had already been cleaned by the time the record was built. Caught by `test_audit_log_never_contains_the_raw_identifier`; the types now come from the policy result.
- `prompt_length` differed between block and redact requests for the same prompt (original versus redacted length). It is now always the redacted length.
- A labeled date of birth is redacted together with its label, so `DOB: 04/17/1968` becomes `[DOB]`. My first test expected the label to stay.

### Verified output

```
$ python -m pytest tests -q
67 passed, 3 skipped          # the 3 skipped need a local Redis

$ scripts/controls_check.sh
36 passed in 0.25s
ok: no raw identifiers in the audit file
OK: 3 entries, head <sha256>
verifier output on the tampered copy: FAIL: seq 2: entry hash does not match its contents
ok: tampered chain rejected
ok: no secrets detected in tracked files
All controls passed.
```

I also checked that the gate can fail: a planted fake AWS key made the secrets scan exit 1, and disabling the substitution in `redact()` made `controls_check.sh` exit 1.

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
It detects phrases, not whether an answer is correct. Cached answers use the same heuristic and keep the human-review requirement.

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
  sensitive.py              identifier detection, redaction, log redaction
  classification.py         per-client allow / redact / block policy
  audit_chain.py            hash-chained, encrypted audit trail plus verifier CLI
  metrics.py                Prometheus counters/histograms
  gateway.py                orchestrates the full pipeline
  app.py                    FastAPI service
docker-compose.yml          local Redis for the optional cache backend
tests/                       unit and Redis integration tests (pytest)
scripts/smoke_test.sh        black-box smoke test against a running instance
docs/                         architecture, security, cost, troubleshooting, portfolio summary
```

Optional paid help: [scoped gateway reviews](SUPPORT.md). Security reports: [private reporting policy](SECURITY.md).
