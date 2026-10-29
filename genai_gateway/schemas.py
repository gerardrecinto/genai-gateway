"""Request/response contracts for the gateway."""

from pydantic import BaseModel, Field


class GatewayRequest(BaseModel):
    client_id: str = Field(min_length=1, max_length=128)
    prompt: str = Field(min_length=1, max_length=8000)
    context: dict[str, str] = Field(default_factory=dict, description="Reserved; not forwarded to providers or cache keys.")


class GatewayResponse(BaseModel):
    request_id: str
    decision_source: str  # "policy_block" | "cache" | "retrieval" | "model" | "fallback"
    text: str
    high_confidence: bool
    needs_human_review: bool
    blocked_reason: str | None = None
    provider_name: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    latency_ms: dict[str, float] = Field(default_factory=dict)
