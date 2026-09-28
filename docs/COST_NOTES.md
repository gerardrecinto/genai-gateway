# Cost notes

## Design decisions and their cost rationale

- **Policy and retrieval run before any model call.** This is the primary
  cost lever in the whole design: a blocked or KB-resolved request costs
  microseconds of CPU, not a model invocation. In a real deployment with
  paid API calls, this is the difference between paying for every request
  and paying only for the ones that actually need generation.
- **Caching avoids repeat model calls for repeat questions.**
  `cache/cache_backend.py` keys on `(prompt, retrieved_context)`, so two
  clients asking the same resolved question hit the cache on the second
  request, not the model, regardless of `client_id`. TTL defaults to 300s
  (`CACHE_TTL_SECONDS` env var) — tunable per how fast the underlying
  answers actually change.
- **In-memory cache as the zero-infrastructure default.** Redis is
  optional (`REDIS_URL` env var); a single-instance deployment or local
  dev loop doesn't need to run and pay for a Redis instance at all.
  `get_cache_backend()` fails open to in-memory if Redis is configured but
  unreachable, rather than failing every request.
- **Rate limiting protects against runaway cost from a single client**,
  not just abuse — a client stuck in a retry loop hits 429s instead of
  generating unbounded model calls.
- **Approximate token counting (`providers/base.py::approximate_token_count`)
  has no tokenizer dependency** (no `tiktoken` or model-specific vocab)
  — a whitespace-split estimate is enough for *relative* cost tracking in
  a portfolio project. Explicitly not billing-accurate; a real deployment
  should use the provider's actual usage response (see
  `AnthropicProvider.generate`, which does use real `response.usage`
  when that path is actually exercised).

## What would cost money if the real provider path were used

- Every request reaching `decision_source: "model"` with `AnthropicProvider`
  active would incur real API cost, scaled by prompt + completion tokens.
- An optional managed Redis (e.g., ElastiCache) instead of local Docker
  Redis, sized for whatever request volume actually needs shared caching
  across multiple gateway instances — not needed for this single-instance
  portfolio setup.

Nothing in this project has incurred real API or cloud cost — `MockProvider`
is the only provider path exercised in the test suite and smoke test, and
Redis here is a local Docker container, not a managed cloud instance.
