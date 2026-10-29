# Portfolio summary

This is an independently built local gateway. It demonstrates policy and structured retrieval before a model call with a deterministic mock provider.

## Claims backed by this repository

- Implemented a provider interface with local mock generation, policy checks, and a hand-authored runbook lookup.
- Added Redis-backed response caching with an in-memory option and graceful cache-outage handling.
- Kept the same human-review heuristic on generated and cached answers.
- Added per-client token buckets, request IDs, stage timings, Prometheus metrics, and audit records without raw prompt or response text.
- Added CI that requires real Redis integration tests and checks the local HTTP flow, audit output, lint, and dependency advisories.

See the current [Gateway checks](https://github.com/gerardrecinto/genai-gateway/actions/workflows/ci.yml) for results. Local runs without Redis skip those integration tests explicitly.

## Limits to explain in an interview

The rate limiter trusts a caller-supplied client ID and is process-local. It is not authentication or a shared spending limit. Policy checks are literal regular expressions. Retrieval uses three hand-authored entries and substring matching. Confidence is a hedging-phrase heuristic, not a calibrated probability or correctness check.

The Anthropic adapter has not been exercised against the real API. It still needs SDK, model-selection, and integration validation. A one-line provider swap does not establish that those requirements are met.

This repository does not establish production operation, users, professional deployment of related projects, paid-provider use, measured cost savings, or a latency target.
