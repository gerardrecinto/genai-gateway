# Portfolio summary

## What this is

An independently built provider-agnostic GenAI gateway demonstrating the
production pattern for putting an LLM behind deterministic guardrails:
policy checks and structured retrieval run first, a model call happens
only when neither resolves the request, and every path — including
blocked and fallback paths — is cached, rate-limited, traced, and
audit-logged.

## Resume bullets (accurate language only)

- Built a provider-agnostic GenAI gateway applying policy checks and
  structured retrieval before any model call, cutting model invocations
  for requests a deterministic layer can already resolve.
- Implemented Redis-backed response caching with an in-memory fallback
  behind one interface, verified against a live local Redis instance.
- Designed a confidence/escalation heuristic that flags low-confidence
  model responses for human review rather than returning them unflagged.
- Implemented per-client rate limiting, request tracing with per-stage
  latency breakdown, Prometheus metrics, and audit logging that never
  persists raw prompt or response content.

**Not used, and why**: "operated in production," "served [N] requests,"
"reduced API cost by [X]%" — none of these are true for this project. No
paid model API was called; `MockProvider` is the only provider exercised.

## Interview talking points

**"Why policy and retrieval before the model, not after?"**
Cost and auditability both point the same direction. A blocked or
KB-resolved request costs microseconds of CPU, and its "reasoning" is a
named rule or a hand-authored answer you can point to directly. Running
the checks after generation would mean paying for a model call on every
request regardless of whether it needed one, and would mean a policy
violation had already reached the model at least once before being caught.

**"How does this relate to your production RAIL work?"**
Directly. `ci-triage` and `devops-mcp` use the same rules-first,
LLM-only-for-what's-left philosophy at a smaller scope (CI failure
classification, incident triage). This project generalizes that pattern
into a standalone gateway shape: policy, retrieval, cache, then model,
with the same principle underneath each stage's ordering.

**"What's the weakest part of this design?"**
Two things, honestly. First, `client_id` is self-reported with no
authentication behind it, which defeats the rate limiter as a real
security control even though it still works as a fairness control
(`docs/SECURITY.md`). Second, the retrieval layer's weak-keyword matching
is plain substring matching, which has real false-positive potential on
unrelated prompts that happen to share a word (`docs/TROUBLESHOOTING.md`
has a concrete example). Both are named gaps, not hidden ones.

**"Have you run this against a real model API in production?"**
No. `MockProvider` is what every test and the smoke test exercise.
`AnthropicProvider` implements the same interface and would work with a
real API key, but it has never been called in this project — that's
stated directly in its own docstring and in the README, not glossed over.

## Claims this project supports

- Hands-on design and implementation of a rules-before-model gateway
  pattern
- Working Redis-backed caching, verified against a live local instance
  (not mocked in that specific test)
- Rate limiting, tracing, metrics, and audit logging that are all live
  and unit/integration tested (30 tests passing)
- A provider abstraction that swaps a mock for a real provider with a
  one-line change, with the real-provider adapter shape written (not
  exercised)

## Claims this project does NOT support

- Any real paid-API model usage
- Production traffic or real users
- Authentication/authorization on the gateway itself
- A trained or ML-based content policy classifier (regex only)
