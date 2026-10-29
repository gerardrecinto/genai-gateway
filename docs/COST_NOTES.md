# Cost and usage notes

The checked-in API, browser demo, tests, and smoke flow use `MockProvider`. They need no paid model API or managed Redis.

A policy block, strong runbook match, or cached answer avoids a provider call. The tests establish these code paths. They do not establish dollar savings or a latency target with a real model provider.

Cache keys use the prompt and retrieved context. The default TTL is 300 seconds, configurable through `CACHE_TTL_SECONDS`. Request `context` is reserved and does not affect the provider or cache key.

The process-local token bucket limits requests for a given caller-supplied client ID. It does not authenticate that identity or enforce a shared spending budget.

The [token estimator](../genai_gateway/providers/base.py) is approximate. It is not suitable for billing. The unverified Anthropic adapter reads reported usage when available, but that code still needs integration validation.

Using a paid provider or managed cache would add costs that this repository does not measure. The local mock path is an evaluation example, not a revenue forecast or a statement about historical billing.
