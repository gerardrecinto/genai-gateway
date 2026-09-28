"""Request-scoped correlation id and per-stage latency timing."""

import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field


@dataclass
class RequestTrace:
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    stage_latency_ms: dict[str, float] = field(default_factory=dict)

    @contextmanager
    def stage(self, name: str):
        start = time.perf_counter()
        try:
            yield
        finally:
            self.stage_latency_ms[name] = round((time.perf_counter() - start) * 1000, 3)
