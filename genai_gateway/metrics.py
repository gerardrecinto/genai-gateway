"""Prometheus metrics. A boring, standard choice over hand-rolled counters."""

from prometheus_client import Counter, Histogram

REQUESTS_TOTAL = Counter(
    "gateway_requests_total", "Total gateway requests by decision source", ["decision_source"]
)
REQUEST_LATENCY_SECONDS = Histogram(
    "gateway_request_latency_seconds", "End-to-end request latency by decision source", ["decision_source"]
)
TOKENS_TOTAL = Counter(
    "gateway_tokens_total", "Approximate tokens processed", ["kind"]  # kind: prompt | completion
)
RATE_LIMITED_TOTAL = Counter("gateway_rate_limited_total", "Requests rejected by the rate limiter")
POLICY_BLOCKED_TOTAL = Counter(
    "gateway_policy_blocked_total", "Requests blocked by policy", ["reason"]
)
