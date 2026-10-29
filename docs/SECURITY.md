# Security notes

For private reports, use the [security policy](../SECURITY.md).

## Implemented controls

- Schema validation and the rate limiter run before policy. Policy checks run before cache, retrieval, and provider access. A matching block never reaches the provider.
- Model responses are checked for empty text, excessive length, and specific leaked-prompt markers before they are cached or returned.
- Generated and cached answers use the same hedging-phrase heuristic for human review. That heuristic does not determine correctness.
- Audit records omit raw prompt and response text. They contain a truncated prompt hash and lengths. The caller-supplied `client_id` is logged verbatim, so it should not contain credentials or personal data. A hash is not an anonymity guarantee.
- The optional local Redis container is bound to loopback. It has no authentication configured.

## Limits

The API and metrics endpoint have no authentication. The caller chooses `client_id`, so the per-client token bucket is a fairness mechanism, not an authenticated security control. Its state is process-local.

Policy rules are literal regular expressions, not a complete prompt-injection defense. The tests cover specific strings. A model response passing the validator is not proof that the response is safe or correct.

The cache stores answer text and is shared across callers. This demo does not implement tenant isolation, a production cache access policy, managed secrets, or an audit retention service.

`AnthropicProvider` reads an API key from the environment and requires an optional SDK. That adapter has not been exercised against a live provider in this project.
