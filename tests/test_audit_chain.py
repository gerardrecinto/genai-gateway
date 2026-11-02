import json
import subprocess
import sys
import threading

import pytest

from genai_gateway.audit_chain import (
    AuditChain,
    AuditWriteError,
    generate_key,
    read_entries,
    verify_chain,
)
from genai_gateway.cache.cache_backend import InMemoryCache
from genai_gateway.gateway import GatewayRequest, GenAIGateway
from genai_gateway.providers.mock_provider import MockProvider
from genai_gateway.rate_limit.token_bucket import TokenBucketLimiter

SSN = "123-45-6789"  # synthetic


@pytest.fixture
def key():
    return generate_key()


@pytest.fixture
def chain_path(tmp_path):
    return str(tmp_path / "chain.jsonl")


def fill(chain, n=5):
    for i in range(n):
        chain.append({"request_id": f"r{i}", "note": f"entry {i}"})


def lines(path):
    with open(path) as f:
        return f.read().splitlines()


def write_lines(path, ls):
    with open(path, "w") as f:
        f.write("\n".join(ls) + "\n")


def test_clean_chain_verifies(chain_path, key):
    fill(AuditChain(chain_path, key))
    result = verify_chain(chain_path, key=key)
    assert result.ok and result.entries == 5


def test_editing_an_entry_is_detected(chain_path, key):
    fill(AuditChain(chain_path, key))
    ls = lines(chain_path)
    e = json.loads(ls[2])
    e["ts"] = "2000-01-01T00:00:00+00:00"
    ls[2] = json.dumps(e)
    write_lines(chain_path, ls)
    result = verify_chain(chain_path)
    assert not result.ok and result.bad_seq == 3


def test_deleting_a_middle_entry_is_detected(chain_path, key):
    fill(AuditChain(chain_path, key))
    ls = lines(chain_path)
    del ls[2]
    write_lines(chain_path, ls)
    assert not verify_chain(chain_path).ok


def test_reordering_is_detected(chain_path, key):
    fill(AuditChain(chain_path, key))
    ls = lines(chain_path)
    ls[1], ls[2] = ls[2], ls[1]
    write_lines(chain_path, ls)
    assert not verify_chain(chain_path).ok


def test_tail_truncation_needs_an_anchor(chain_path, key):
    chain = AuditChain(chain_path, key)
    fill(chain)
    anchored_head = chain.head
    write_lines(chain_path, lines(chain_path)[:3])
    assert verify_chain(chain_path).ok  # internally consistent, so plain verify cannot see it
    assert not verify_chain(chain_path, expected_count=5).ok
    assert not verify_chain(chain_path, expected_head=anchored_head).ok


def test_rehashed_forgery_passes_without_key_and_fails_with_key(chain_path, key):
    from genai_gateway.audit_chain import _entry_hash

    fill(AuditChain(chain_path, key), n=3)
    ls = lines(chain_path)
    e = json.loads(ls[1])
    e["payload"] = "not-a-real-token"
    e["hash"] = _entry_hash(e["seq"], e["ts"], e["prev"], e["payload"])
    ls[1] = json.dumps(e)
    # keep the later link consistent so only the payload is forged
    e2 = json.loads(ls[2])
    e2["prev"] = e["hash"]
    e2["hash"] = _entry_hash(e2["seq"], e2["ts"], e2["prev"], e2["payload"])
    ls[2] = json.dumps(e2)
    write_lines(chain_path, ls)
    assert verify_chain(chain_path).ok
    assert not verify_chain(chain_path, key=key).ok


def test_wrong_key_fails(chain_path, key):
    fill(AuditChain(chain_path, key))
    assert not verify_chain(chain_path, key=generate_key()).ok


def test_chain_resumes_after_restart(chain_path, key):
    fill(AuditChain(chain_path, key), n=2)
    again = AuditChain(chain_path, key)
    fill(again, n=2)
    result = verify_chain(chain_path, key=key)
    assert result.ok and result.entries == 4


def test_concurrent_appends_keep_the_chain_valid(chain_path, key):
    chain = AuditChain(chain_path, key)
    threads = [threading.Thread(target=fill, args=(chain, 10)) for _ in range(8)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    result = verify_chain(chain_path, key=key)
    assert result.ok and result.entries == 80


def make_gateway(chain):
    return GenAIGateway(
        provider=MockProvider(),
        cache=InMemoryCache(),
        rate_limiter=TokenBucketLimiter(capacity=50, refill_per_second=0),
        audit_chain=chain,
    )


def test_gateway_writes_one_encrypted_entry_per_request(chain_path, key):
    gw = make_gateway(AuditChain(chain_path, key))
    gw.handle(GatewayRequest(client_id="c1", prompt=f"Check the record for SSN {SSN} and DOB: 04/17/1968"))
    gw.handle(GatewayRequest(client_id="c1", prompt="How do I roll back a deployment"))
    assert verify_chain(chain_path, key=key).entries == 2

    raw = open(chain_path).read()
    assert SSN not in raw and "04/17/1968" not in raw
    assert "Check the record" not in raw  # payload is ciphertext, not readable text

    first = read_entries(chain_path, key)[0]
    assert first["redacted_prompt"] == "Check the record for SSN [SSN] and [DOB]"
    assert SSN not in json.dumps(first)


def test_gateway_fails_closed_when_the_trail_cannot_be_written(tmp_path, key):
    gw = make_gateway(AuditChain(str(tmp_path / "no_such_dir" / "chain.jsonl"), key))
    with pytest.raises(AuditWriteError):
        gw.handle(GatewayRequest(client_id="c1", prompt="How do I roll back a deployment"))


def test_cli_exit_codes(chain_path, key, monkeypatch):
    fill(AuditChain(chain_path, key))
    env = {"AUDIT_KEY": key, "PATH": ""}
    ok = subprocess.run([sys.executable, "-m", "genai_gateway.audit_chain", "verify", chain_path, "--key-env", "AUDIT_KEY"],
                        capture_output=True, text=True, env=env)
    assert ok.returncode == 0 and "OK: 5 entries" in ok.stdout
    ls = lines(chain_path)
    e = json.loads(ls[0])
    e["ts"] = "tampered"
    ls[0] = json.dumps(e)
    write_lines(chain_path, ls)
    bad = subprocess.run([sys.executable, "-m", "genai_gateway.audit_chain", "verify", chain_path],
                         capture_output=True, text=True, env=env)
    assert bad.returncode == 1 and "FAIL" in bad.stderr
