import logging

import pytest

from genai_gateway import sensitive
from genai_gateway.policy.rules import evaluate_policy
from genai_gateway.sensitive import install_log_redaction, redact

# All values below are synthetic. None belong to a real person.


@pytest.mark.parametrize(
    "text,expected_type",
    [
        ("SSN 123-45-6789 on file", "ssn"),
        ("card 4111 1111 1111 1111 expired", "credit_card"),
        ("write to pat.example@example.org", "email"),
        ("call (619) 555-0142 tomorrow", "phone"),
        ("call 619-555-0142 tomorrow", "phone"),
        ("MRN: 00482913 admitted", "mrn"),
        ("medical record number 99120045", "mrn"),
        ("DOB: 04/17/1968 per intake", "dob"),
        ("date of birth 4-17-68", "dob"),
    ],
)
def test_each_identifier_is_detected_and_redacted(text, expected_type):
    assert expected_type in evaluate_policy(text).pii_types_detected
    result = redact(text)
    assert f"[{expected_type.upper()}]" in result.text
    assert result.counts[expected_type] >= 1


def test_redaction_removes_every_synthetic_value():
    text = "Patient MRN 00482913, DOB 04/17/1968, SSN 123-45-6789, phone 619-555-0142, pat@example.org"
    out = redact(text).text
    for raw in ("00482913", "04/17/1968", "123-45-6789", "619-555-0142", "pat@example.org"):
        assert raw not in out


def test_benign_technical_text_is_left_alone():
    text = "Upgrade to v1.29.4 on port 8080, build 482913, rollout took 75 seconds at 10.0.3.14"
    assert redact(text).text == text
    assert evaluate_policy(text).pii_types_detected == []


def test_ssn_is_not_also_counted_as_phone():
    result = redact("123-45-6789")
    assert result.counts == {"ssn": 1}


def test_redaction_is_idempotent():
    once = redact("SSN 123-45-6789").text
    assert redact(once).text == once


def test_log_redaction_covers_arbitrary_loggers(caplog):
    previous = logging.getLogRecordFactory()
    sensitive._installed = False
    try:
        install_log_redaction()
        with caplog.at_level(logging.INFO):
            logging.getLogger("some.other.module").info("lookup failed for %s", "123-45-6789")
        assert "123-45-6789" not in caplog.text
        assert "[SSN]" in caplog.text
    finally:
        logging.setLogRecordFactory(previous)
        sensitive._installed = False
