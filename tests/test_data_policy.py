import json
import logging

import pytest

from genai_gateway.cache.cache_backend import InMemoryCache
from genai_gateway.classification import ClassificationPolicy
from genai_gateway.gateway import GenAIGateway
from genai_gateway.providers.base import ProviderResponse
from genai_gateway.rate_limit.token_bucket import TokenBucketLimiter
from genai_gateway.schemas import GatewayRequest

SSN = "123-45-6789"  # synthetic


class RecordingProvider:
    def __init__(self):
        self.seen = []

    def generate(self, prompt, context=None):
        self.seen.append(prompt)
        return ProviderResponse(text="Here is a plain answer.", provider_name="rec", prompt_tokens=1, completion_tokens=1)


def make(policy=None, provider=None):
    provider = provider or RecordingProvider()
    gw = GenAIGateway(
        provider=provider,
        cache=InMemoryCache(),
        rate_limiter=TokenBucketLimiter(capacity=50, refill_per_second=0),
        classification=policy,
    )
    return gw, provider


def req(prompt, client="c1"):
    return GatewayRequest(client_id=client, prompt=prompt)


def test_default_redacts_before_the_model_sees_the_prompt():
    gw, provider = make()
    gw.handle(req(f"Summarize the ticket for SSN {SSN}"))
    assert SSN not in provider.seen[0]
    assert "[SSN]" in provider.seen[0]


def test_allow_passes_the_prompt_through():
    gw, provider = make(ClassificationPolicy(default="allow"))
    gw.handle(req(f"Summarize the ticket for SSN {SSN}"))
    assert SSN in provider.seen[0]


def test_block_refuses_and_never_calls_the_model():
    gw, provider = make(ClassificationPolicy(default="block"))
    resp = gw.handle(req(f"Summarize the ticket for SSN {SSN}"))
    assert resp.decision_source == "policy_block"
    assert resp.blocked_reason == "sensitive_data_blocked"
    assert provider.seen == []


def test_block_does_not_affect_clean_prompts():
    gw, provider = make(ClassificationPolicy(default="block"))
    resp = gw.handle(req("How do I roll back a deployment safely"))
    assert resp.decision_source == "model"


def test_per_client_override():
    policy = ClassificationPolicy(default="redact", per_client={"clinic-app": "block", "internal-tool": "allow"})
    assert policy.mode_for("clinic-app") == "block"
    assert policy.mode_for("internal-tool") == "allow"
    assert policy.mode_for("anyone-else") == "redact"


def test_invalid_mode_is_rejected_at_startup():
    with pytest.raises(ValueError):
        ClassificationPolicy(default="mask")
    with pytest.raises(ValueError):
        ClassificationPolicy(per_client={"a": "nope"})


def test_from_env(monkeypatch):
    monkeypatch.setenv("GATEWAY_DATA_POLICY", json.dumps({"default": "block", "clients": {"a": "allow"}}))
    policy = ClassificationPolicy.from_env()
    assert policy.mode_for("a") == "allow"
    assert policy.mode_for("b") == "block"


def test_redacted_prompts_share_one_cache_entry():
    gw, provider = make()
    first = gw.handle(req("Explain the status for SSN 123-45-6789 please"))
    second = gw.handle(req("Explain the status for SSN 987-65-4321 please"))
    assert first.decision_source == "model"
    assert second.decision_source == "cache"
    assert len(provider.seen) == 1


def test_audit_log_never_contains_the_raw_identifier(caplog):
    gw, _ = make()
    with caplog.at_level(logging.INFO, logger="genai_gateway.audit"):
        gw.handle(req(f"Summarize the ticket for SSN {SSN}"))
    assert caplog.records
    assert SSN not in caplog.text
    record = json.loads(caplog.records[-1].getMessage())
    assert record["redacted_types"] == ["ssn"]
    assert record["classification_mode"] == "redact"


def test_prompt_hash_ignores_the_identifier_value():
    # Regression: the hash used to be computed over the raw prompt, so an
    # SSN could be recovered by hashing guesses against the log.
    gw, _ = make()
    hashes = []
    for ssn in ("123-45-6789", "987-65-4321"):
        with_logs = []
        handler = logging.Handler()
        handler.emit = lambda r, store=with_logs: store.append(json.loads(r.getMessage()))
        audit = logging.getLogger("genai_gateway.audit")
        audit.addHandler(handler)
        audit.setLevel(logging.INFO)
        try:
            gw.handle(req(f"Look up SSN {ssn} for me", client=f"c-{ssn}"))
        finally:
            audit.removeHandler(handler)
        hashes.append(with_logs[-1]["prompt_hash"])
    assert hashes[0] == hashes[1]
