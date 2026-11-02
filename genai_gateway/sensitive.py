"""Detect and redact sensitive identifiers (synthetic PHI/PII shapes).

Pattern based, so it catches identifiers that look like identifiers: SSNs,
card numbers, emails, phone numbers, medical record numbers and dates of
birth that follow a label. It does NOT find free-text names, addresses or
diagnoses. See the README limits section.
"""

import logging
from dataclasses import dataclass, field

from genai_gateway.policy.rules import PII_PATTERNS

PLACEHOLDERS = {name: f"[{name.upper()}]" for name in PII_PATTERNS}


@dataclass
class RedactionResult:
    text: str
    counts: dict[str, int] = field(default_factory=dict)

    @property
    def types(self) -> list[str]:
        return list(self.counts)


def redact(text: str) -> RedactionResult:
    counts: dict[str, int] = {}
    for name, pattern in PII_PATTERNS.items():
        text, n = pattern.subn(PLACEHOLDERS[name], text)
        if n:
            counts[name] = n
    return RedactionResult(text=text, counts=counts)


_installed = False


def install_log_redaction() -> None:
    """Redact every log record's message as the record is created.

    Done in the record factory so it covers every logger and handler in the
    process, including ones added later, without each caller remembering.
    """
    global _installed
    if _installed:
        return
    previous = logging.getLogRecordFactory()

    def factory(*args, **kwargs):
        record = previous(*args, **kwargs)
        try:
            record.msg = redact(record.getMessage()).text
            record.args = ()
        except Exception:
            pass
        return record

    logging.setLogRecordFactory(factory)
    _installed = True
