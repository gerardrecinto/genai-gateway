"""Drive the real FastAPI app with synthetic sensitive prompts, then prove
the audit trail catches tampering. Used by scripts/controls_check.sh.

Everything here is synthetic. Exits non-zero if any control fails.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile

from cryptography.fernet import Fernet

tmp = tempfile.mkdtemp()
chain = os.path.join(tmp, "chain.jsonl")
key = Fernet.generate_key().decode()
os.environ.update(
    GATEWAY_AUDIT_CHAIN_PATH=chain,
    GATEWAY_AUDIT_KEY=key,
    GATEWAY_DATA_POLICY=json.dumps({"default": "redact", "clients": {"clinic-app": "block"}}),
)

from fastapi.testclient import TestClient  # noqa: E402

from genai_gateway.app import app  # noqa: E402

SYNTHETIC = ["123-45-6789", "00482913", "04/17/1968", "619-555-0142", "pat.example@example.org"]
client = TestClient(app)


def post(client_id, prompt):
    r = client.post("/generate", json={"client_id": client_id, "prompt": prompt})
    r.raise_for_status()
    return r.json()


def fail(msg):
    print(f"FAIL: {msg}")
    sys.exit(1)


prompt = "Summarize the intake: MRN 00482913, DOB: 04/17/1968, SSN 123-45-6789, phone 619-555-0142, pat.example@example.org"
a = post("portal", prompt)
b = post("clinic-app", prompt)
c = post("portal", "How do I roll back a Kubernetes deployment?")
if b["blocked_reason"] != "sensitive_data_blocked":
    fail("clinic-app should be blocked")
if a["decision_source"] == "policy_block" or c["decision_source"] == "policy_block":
    fail("redact and clean requests should not be blocked")

raw = open(chain).read()
leaked = [v for v in SYNTHETIC if v in raw]
if leaked:
    fail(f"raw synthetic values found in the audit file: {leaked}")
print("ok: no raw identifiers in the audit file")

mod = [sys.executable, "-m", "genai_gateway.audit_chain"]
env = {**os.environ, "AUDIT_KEY": key}
out = subprocess.run([*mod, "verify", chain, "--key-env", "AUDIT_KEY", "--expect-count", "3"], capture_output=True, text=True, env=env)
print(out.stdout.strip() or out.stderr.strip())
if out.returncode != 0:
    fail("clean chain did not verify")

lines = open(chain).read().splitlines()
bad = os.path.join(tmp, "tampered.jsonl")
e = json.loads(lines[1])
e["ts"] = "1999-01-01T00:00:00+00:00"
lines[1] = json.dumps(e)
open(bad, "w").write("\n".join(lines) + "\n")
out = subprocess.run([*mod, "verify", bad], capture_output=True, text=True, env=env)
print("verifier output on the tampered copy: " + out.stderr.strip())
if out.returncode == 0:
    fail("tampered chain verified, which should not happen")
print("ok: tampered chain rejected")
shutil.rmtree(tmp)
