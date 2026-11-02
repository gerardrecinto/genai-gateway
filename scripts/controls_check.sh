#!/usr/bin/env bash
# The sensitive-data controls, run as one gate. Used locally and in CI.
set -euo pipefail
cd "$(dirname "$0")/.."
echo "== 1. redaction, data policy and audit chain tests"
python -m pytest tests/test_sensitive.py tests/test_data_policy.py tests/test_audit_chain.py -q
echo "== 2. end-to-end audit trail: no raw identifiers, tamper detection"
python scripts/audit_demo.py
echo "== 3. secrets scan"
scripts/check_secrets.sh
echo "All controls passed."
