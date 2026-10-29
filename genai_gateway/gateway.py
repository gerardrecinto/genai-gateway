"""Core orchestration: policy -> cache -> retrieval -> model -> validation.

Each stage can end the request early. A request that reaches the model
call has already survived policy checks, a cache miss, and a retrieval
non-resolve — the model is the last resort, not the default path.
"""

import hashlib
import json
import logging
import time

from genai_gateway import metrics
from genai_gateway.audit import build_audit_record, emit_audit_log
from genai_gateway.cache.cache_backend import CacheBackend
from genai_gateway.policy.rules import evaluate_policy
from genai_gateway.providers.base import ModelProvider
from genai_gateway.rate_limit.token_bucket import TokenBucketLimiter
from genai_gateway.retrieval.knowledge_base import match_knowledge_base
from genai_gateway.schemas import GatewayRequest, GatewayResponse
from genai_gateway.tracing import RequestTrace

logger = logging.getLogger(__name__)

HEDGING_PHRASES = [
    "i don't have enough context",
    "i'm not sure",
    "could you provide more detail",
    "it depends",
]

MAX_RESPONSE_LENGTH = 4000
LEAKED_PROMPT_MARKERS = ["system prompt:", "you are an ai language model instructed to"]


class RateLimitExceeded(Exception):
    pass


def build_cache_key(prompt: str, context: str | None) -> str:
    payload = json.dumps({"prompt": prompt, "context": context}, sort_keys=True)
    return "gw:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def validate_response(text: str) -> bool:
    if not text or not text.strip():
        return False
    if len(text) > MAX_RESPONSE_LENGTH:
        return False
    lowered = text.lower()
    return not any(marker in lowered for marker in LEAKED_PROMPT_MARKERS)


def assess_confidence(text: str) -> bool:
    lowered = text.lower()
    return not any(phrase in lowered for phrase in HEDGING_PHRASES)


class GenAIGateway:
    def __init__(
        self,
        provider: ModelProvider,
        cache: CacheBackend,
        rate_limiter: TokenBucketLimiter,
        cache_ttl_seconds: int = 300,
    ):
        self.provider = provider
        self.cache = cache
        self.rate_limiter = rate_limiter
        self.cache_ttl_seconds = cache_ttl_seconds

    def handle(self, request: GatewayRequest) -> GatewayResponse:
        trace = RequestTrace()
        start = time.perf_counter()

        if not self.rate_limiter.allow(request.client_id):
            metrics.RATE_LIMITED_TOTAL.inc()
            raise RateLimitExceeded(f"rate limit exceeded for client_id={request.client_id}")

        with trace.stage("policy"):
            policy_result = evaluate_policy(request.prompt)

        if policy_result.blocked:
            return self._finish(
                request=request,
                trace=trace,
                start=start,
                decision_source="policy_block",
                text="Request blocked by policy.",
                high_confidence=True,
                needs_human_review=False,
                blocked_reason=policy_result.reason,
                pii_types=policy_result.pii_types_detected,
                cache_key=None,
            )

        context_for_model: str | None = None
        with trace.stage("retrieval"):
            kb_match = match_knowledge_base(request.prompt)
        cache_key = build_cache_key(request.prompt, kb_match.text if kb_match.decision == "enrich" else None)

        with trace.stage("cache_lookup"):
            cached_text = self._read_cache(cache_key)
        if cached_text is not None:
            confident = assess_confidence(cached_text)
            return self._finish(
                request=request,
                trace=trace,
                start=start,
                decision_source="cache",
                text=cached_text,
                high_confidence=confident,
                needs_human_review=not confident,
                blocked_reason=None,
                pii_types=policy_result.pii_types_detected,
                cache_key=cache_key,
                skip_cache_write=True,
            )

        if kb_match.decision == "resolve":
            self._write_cache(cache_key, kb_match.text)
            return self._finish(
                request=request,
                trace=trace,
                start=start,
                decision_source="retrieval",
                text=kb_match.text,
                high_confidence=True,
                needs_human_review=False,
                blocked_reason=None,
                pii_types=policy_result.pii_types_detected,
                cache_key=cache_key,
                skip_cache_write=True,
            )

        if kb_match.decision == "enrich":
            context_for_model = kb_match.text

        with trace.stage("model_call"):
            try:
                provider_response = self.provider.generate(request.prompt, context_for_model)
            except Exception:
                return self._finish(
                    request=request,
                    trace=trace,
                    start=start,
                    decision_source="fallback",
                    text="The model is temporarily unavailable. Please try again shortly.",
                    high_confidence=False,
                    needs_human_review=True,
                    blocked_reason="provider_error",
                    pii_types=policy_result.pii_types_detected,
                    cache_key=None,
                )

        with trace.stage("response_validation"):
            valid = validate_response(provider_response.text)

        if not valid:
            return self._finish(
                request=request,
                trace=trace,
                start=start,
                decision_source="fallback",
                text="The generated response failed validation and was withheld.",
                high_confidence=False,
                needs_human_review=True,
                blocked_reason="response_validation_failed",
                pii_types=policy_result.pii_types_detected,
                cache_key=None,
                provider_name=provider_response.provider_name,
                prompt_tokens=provider_response.prompt_tokens,
                completion_tokens=provider_response.completion_tokens,
            )

        confident = assess_confidence(provider_response.text)
        self._write_cache(cache_key, provider_response.text)

        return self._finish(
            request=request,
            trace=trace,
            start=start,
            decision_source="model",
            text=provider_response.text,
            high_confidence=confident,
            needs_human_review=not confident,
            blocked_reason=None,
            pii_types=policy_result.pii_types_detected,
            cache_key=cache_key,
            skip_cache_write=True,
            provider_name=provider_response.provider_name,
            prompt_tokens=provider_response.prompt_tokens,
            completion_tokens=provider_response.completion_tokens,
        )

    def _read_cache(self, key: str) -> str | None:
        try:
            return self.cache.get(key)
        except Exception:
            logger.warning("Cache read unavailable; continuing without a cached answer")
            return None

    def _write_cache(self, key: str, text: str) -> None:
        try:
            self.cache.set(key, text, self.cache_ttl_seconds)
        except Exception:
            logger.warning("Cache write unavailable; returning the answer without caching")

    def _finish(
        self,
        *,
        request: GatewayRequest,
        trace: RequestTrace,
        start: float,
        decision_source: str,
        text: str,
        high_confidence: bool,
        needs_human_review: bool,
        blocked_reason: str | None,
        pii_types: list[str],
        cache_key: str | None,
        skip_cache_write: bool = False,
        provider_name: str | None = None,
        prompt_tokens: int | None = None,
        completion_tokens: int | None = None,
    ) -> GatewayResponse:
        total_latency_ms = round((time.perf_counter() - start) * 1000, 3)

        metrics.REQUESTS_TOTAL.labels(decision_source=decision_source).inc()
        metrics.REQUEST_LATENCY_SECONDS.labels(decision_source=decision_source).observe(total_latency_ms / 1000)
        if decision_source == "policy_block" and blocked_reason:
            metrics.POLICY_BLOCKED_TOTAL.labels(reason=blocked_reason).inc()
        if prompt_tokens is not None:
            metrics.TOKENS_TOTAL.labels(kind="prompt").inc(prompt_tokens)
        if completion_tokens is not None:
            metrics.TOKENS_TOTAL.labels(kind="completion").inc(completion_tokens)

        record = build_audit_record(
            request_id=trace.request_id,
            client_id=request.client_id,
            decision_source=decision_source,
            prompt=request.prompt,
            response_text=text,
            pii_types_detected=pii_types,
            blocked_reason=blocked_reason,
            provider_name=provider_name,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_latency_ms=total_latency_ms,
        )
        emit_audit_log(record)

        return GatewayResponse(
            request_id=trace.request_id,
            decision_source=decision_source,
            text=text,
            high_confidence=high_confidence,
            needs_human_review=needs_human_review,
            blocked_reason=blocked_reason,
            provider_name=provider_name,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            latency_ms=trace.stage_latency_ms,
        )
