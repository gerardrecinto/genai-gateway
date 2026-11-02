"""Tamper-evident, encrypted audit trail.

Each line is one entry. The payload is encrypted (Fernet: AES-128-CBC plus
HMAC-SHA256, from the `cryptography` package). Each entry's hash covers its
sequence number, timestamp, the previous entry's hash and the ciphertext, so
editing, deleting or reordering any line breaks every hash after it.

What this does not give you: if someone can rewrite the whole file, they can
recompute hashes. Verifying with the key catches forged payloads, and
anchoring the head hash somewhere else (expected_head) catches truncation
and full rewrites. Without those, the chain only proves internal consistency.

CLI:
    python -m genai_gateway.audit_chain keygen
    python -m genai_gateway.audit_chain verify PATH [--key-env VAR] [--expect-head H] [--expect-count N]
    python -m genai_gateway.audit_chain head PATH
"""

import argparse
import hashlib
import json
import os
import sys
import threading
from dataclasses import dataclass
from datetime import datetime, timezone

from cryptography.fernet import Fernet, InvalidToken

GENESIS = "0" * 64


class AuditWriteError(Exception):
    pass


def _entry_hash(seq: int, ts: str, prev: str, payload: str) -> str:
    return hashlib.sha256(f"{seq}|{ts}|{prev}|{payload}".encode("utf-8")).hexdigest()


def generate_key() -> str:
    return Fernet.generate_key().decode()


class AuditChain:
    def __init__(self, path: str, key: str | bytes):
        self.path = path
        self._fernet = Fernet(key)
        self._lock = threading.Lock()
        self._seq = 0
        self._head = GENESIS
        if os.path.exists(path) and os.path.getsize(path) > 0:
            with open(path, "rb") as f:
                last = f.read().splitlines()[-1]
            entry = json.loads(last)
            self._seq, self._head = entry["seq"], entry["hash"]

    @property
    def head(self) -> str:
        return self._head

    def append(self, payload: dict) -> dict:
        data = json.dumps(payload, sort_keys=True).encode("utf-8")
        token = self._fernet.encrypt(data).decode()
        with self._lock:
            seq = self._seq + 1
            ts = datetime.now(timezone.utc).isoformat()
            entry = {
                "seq": seq,
                "ts": ts,
                "prev": self._head,
                "payload": token,
                "hash": _entry_hash(seq, ts, self._head, token),
            }
            try:
                with open(self.path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(entry) + "\n")
                    f.flush()
                    os.fsync(f.fileno())
            except OSError as exc:
                raise AuditWriteError(f"could not write audit entry: {exc}") from exc
            self._seq, self._head = seq, entry["hash"]
            return entry


@dataclass
class VerifyResult:
    ok: bool
    entries: int
    head: str
    error: str | None = None
    bad_seq: int | None = None


def verify_chain(
    path: str,
    key: str | bytes | None = None,
    expected_head: str | None = None,
    expected_count: int | None = None,
) -> VerifyResult:
    fernet = Fernet(key) if key else None
    prev = GENESIS
    count = 0
    with open(path, "r", encoding="utf-8") as f:
        for lineno, line in enumerate(f, start=1):
            try:
                e = json.loads(line)
                seq, ts, e_prev, payload, e_hash = e["seq"], e["ts"], e["prev"], e["payload"], e["hash"]
            except (ValueError, KeyError, TypeError):
                return VerifyResult(False, count, prev, f"line {lineno} is not a valid entry", lineno)
            if seq != count + 1:
                return VerifyResult(False, count, prev, f"expected seq {count + 1}, found {seq}", seq)
            if e_prev != prev:
                return VerifyResult(False, count, prev, f"seq {seq}: prev hash does not match", seq)
            if _entry_hash(seq, ts, e_prev, payload) != e_hash:
                return VerifyResult(False, count, prev, f"seq {seq}: entry hash does not match its contents", seq)
            if fernet is not None:
                try:
                    fernet.decrypt(payload.encode())
                except InvalidToken:
                    return VerifyResult(False, count, prev, f"seq {seq}: payload fails authenticated decryption", seq)
            prev, count = e_hash, seq
    if expected_count is not None and count != expected_count:
        return VerifyResult(False, count, prev, f"expected {expected_count} entries, found {count}")
    if expected_head is not None and prev != expected_head:
        return VerifyResult(False, count, prev, "head hash does not match the anchored value")
    return VerifyResult(True, count, prev)


def read_entries(path: str, key: str | bytes) -> list[dict]:
    fernet = Fernet(key)
    out = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            e = json.loads(line)
            out.append({"seq": e["seq"], "ts": e["ts"], **json.loads(fernet.decrypt(e["payload"].encode()))})
    return out


def _main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="audit_chain")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("keygen")
    v = sub.add_parser("verify")
    v.add_argument("path")
    v.add_argument("--key-env", default=None, help="env var holding the key, to also check payloads decrypt")
    v.add_argument("--expect-head")
    v.add_argument("--expect-count", type=int)
    h = sub.add_parser("head")
    h.add_argument("path")
    args = ap.parse_args(argv)

    if args.cmd == "keygen":
        print(generate_key())
        return 0
    if args.cmd == "head":
        r = verify_chain(args.path)
        print(r.head)
        return 0 if r.ok else 1
    key = os.environ.get(args.key_env) if args.key_env else None
    if args.key_env and not key:
        print(f"FAIL: env var {args.key_env} is not set", file=sys.stderr)
        return 2
    r = verify_chain(args.path, key=key, expected_head=args.expect_head, expected_count=args.expect_count)
    if r.ok:
        print(f"OK: {r.entries} entries, head {r.head}")
        return 0
    print(f"FAIL: {r.error}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(_main())
