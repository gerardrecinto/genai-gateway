"""Audit logging. Deliberately never logs the raw prompt or raw response
text — only a hash (for correlating repeated requests) and length. If an
incident needs the actual content, that's a separate, access-controlled
system to build later, not something this log should hold by default.
"""

import hashlib
import json
import logging
from dataclasses import asdict, dataclass

logger = logging.getLogger("genai_gateway.audit")


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


@dataclass
class AuditRecord:
    request_id: str
    client_id: str
    decision_source: str
    prompt_hash: str
    prompt_length: int
    pii_types_detected: list[str]
    response_length: int
    blocked_reason: str | None
    provider_name: str | None
    prompt_tokens: int | None
    completion_tokens: int | None
    total_latency_ms: float


def build_audit_record(
    *,
    request_id: str,
    client_id: str,
    decision_source: str,
    prompt: str,
    response_text: str,
    pii_types_detected: list[str],
    blocked_reason: str | None,
    provider_name: str | None,
    prompt_tokens: int | None,
    completion_tokens: int | None,
    total_latency_ms: float,
) -> AuditRecord:
    return AuditRecord(
        request_id=request_id,
        client_id=client_id,
        decision_source=decision_source,
        prompt_hash=_hash(prompt),
        prompt_length=len(prompt),
        pii_types_detected=pii_types_detected,
        response_length=len(response_text),
        blocked_reason=blocked_reason,
        provider_name=provider_name,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_latency_ms=total_latency_ms,
    )


def emit_audit_log(record: AuditRecord) -> None:
    logger.info(json.dumps(asdict(record)))
