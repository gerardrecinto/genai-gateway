#!/usr/bin/env bash
# Fail if detect-secrets finds anything in tracked files.
set -euo pipefail
found=$(git ls-files -z | xargs -0 detect-secrets scan | python3 -c "
import json, sys
d = json.load(sys.stdin)['results']
for path, hits in d.items():
    for h in hits:
        print(f\"{path}:{h['line_number']} {h['type']}\")
")
if [ -n "$found" ]; then
  echo "Possible secrets found:"; echo "$found"; exit 1
fi
echo "ok: no secrets detected in tracked files"
