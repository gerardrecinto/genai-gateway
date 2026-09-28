# Security notes

## What's implemented

- **Policy checks run before anything else** (`policy/rules.py`) — a
  request that matches a secret-exfiltration or prompt-injection pattern
  never reaches the cache, retrieval, or model. It's the first stage in
  `GenAIGateway.handle()`, not a post-hoc filter.
- **PII is detected but not silently swallowed into logs.** `audit.py`
  never logs the raw prompt or response — only a truncated sha256 hash and
  length. `pii_types_detected` (which category, not the actual value)
  is the only PII-related field that reaches the audit record.
- **Rate limiting is per-client**, not global — one noisy client can't
  starve others' token budget (`rate_limit/token_bucket.py`, keyed by
  `client_id`).
- **Response validation checks for leaked-prompt markers**
  (`gateway.py::validate_response`) before a model response is ever
  returned or cached, catching the case where a model echoes back
  something resembling its own system prompt.

## Known limitations (stated, not hidden)

- **Policy patterns are regex, not a trained classifier.** They catch the
  literal phrasings tested in `tests/test_policy.py` and nothing more
  creative — a determined attacker could rephrase around them. This is a
  first layer, not a complete defense; a production system would want
  this backed by a real classifier or a managed moderation API.
- **No authentication on `/generate` or `/metrics`.** `client_id` is a
  self-reported field in the request body, not derived from an API key or
  session. Anyone can claim any `client_id`, which defeats the per-client
  rate limit as a security control (though it still works as a fairness
  control for well-behaved clients). Adding real auth (API key header,
  mapped to `client_id` server-side) is a clear next step, not implemented.
- **Redis has no auth configured** in `docker-compose.yml` (`redis:7-alpine`
  with default settings) — fine for local dev, not how you'd run it in
  production. See `docs/COST_NOTES.md`'s sibling note in `release-risk-ml`'s
  IaC pattern: a real deployment needs `requirepass` or IAM-based auth (for
  managed Redis) and TLS in transit.
- **`AnthropicProvider` reads `ANTHROPIC_API_KEY` from an environment
  variable**, never hardcoded — but there's no secrets-manager integration
  here since it's never actually invoked in this portfolio.
