"""Deterministic policy layer: runs before cache, retrieval, or any model call.

A blocked prompt never reaches the model, never gets cached, and never
gets retrieval context attached — the point of running this first.
"""

import re
from dataclasses import dataclass, field

SECRET_EXFIL_PATTERNS = [
    re.compile(r"\bprint\s+(the\s+)?(api[_\s-]?key|secret|password|token)\b", re.IGNORECASE),
    re.compile(r"\bdump\s+(all\s+)?(secrets|credentials|env(ironment)?\s*vars?)\b", re.IGNORECASE),
    re.compile(r"\b(aws_secret_access_key|aws_access_key_id)\b", re.IGNORECASE),
]

PROMPT_INJECTION_PATTERNS = [
    re.compile(r"\bignore\s+(all\s+)?(previous|prior|above)\s+instructions\b", re.IGNORECASE),
    re.compile(r"\bdisregard\s+(the\s+)?system\s+prompt\b", re.IGNORECASE),
    re.compile(r"\byou\s+are\s+now\s+(in\s+)?dan\s+mode\b", re.IGNORECASE),
]

PII_PATTERNS = {
    "ssn": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "credit_card": re.compile(r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b"),
    "email": re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"),
}


@dataclass
class PolicyResult:
    blocked: bool
    reason: str | None = None
    pii_types_detected: list[str] = field(default_factory=list)


def evaluate_policy(prompt: str) -> PolicyResult:
    for pattern in SECRET_EXFIL_PATTERNS:
        if pattern.search(prompt):
            return PolicyResult(blocked=True, reason="secret_exfiltration_attempt")

    for pattern in PROMPT_INJECTION_PATTERNS:
        if pattern.search(prompt):
            return PolicyResult(blocked=True, reason="prompt_injection_attempt")

    pii_types = [name for name, pattern in PII_PATTERNS.items() if pattern.search(prompt)]
    # PII is flagged for audit redaction but does not block the request by
    # itself — a support prompt containing an email address is legitimate;
    # blocking it outright would be a false-positive-heavy overreach.
    return PolicyResult(blocked=False, pii_types_detected=pii_types)
