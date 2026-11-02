"""Per-client data handling when a prompt contains sensitive identifiers.

allow  - pass the prompt through unchanged (audit still stores only the
         redacted form)
redact - replace identifiers with placeholders before retrieval, cache and
         the model see the prompt (default)
block  - refuse the request
"""

import json
import os

VALID_MODES = ("allow", "redact", "block")


class ClassificationPolicy:
    def __init__(self, default: str = "redact", per_client: dict[str, str] | None = None):
        per_client = per_client or {}
        for mode in [default, *per_client.values()]:
            if mode not in VALID_MODES:
                raise ValueError(f"unknown data policy mode {mode!r}; use one of {VALID_MODES}")
        self.default = default
        self.per_client = dict(per_client)

    def mode_for(self, client_id: str) -> str:
        return self.per_client.get(client_id, self.default)

    @classmethod
    def from_env(cls, var: str = "GATEWAY_DATA_POLICY") -> "ClassificationPolicy":
        raw = os.environ.get(var)
        if not raw:
            return cls()
        data = json.loads(raw)
        return cls(default=data.get("default", "redact"), per_client=data.get("clients", {}))
