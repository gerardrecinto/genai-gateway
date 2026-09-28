from dataclasses import dataclass
from typing import Protocol


def approximate_token_count(text: str) -> int:
    """Whitespace-split approximation, not a real tokenizer (no tiktoken/BPE
    dependency). Good enough for relative cost tracking in this portfolio
    project; do not treat these numbers as billing-accurate.
    """
    return len(text.split())


@dataclass
class ProviderResponse:
    text: str
    provider_name: str
    prompt_tokens: int
    completion_tokens: int


class ModelProvider(Protocol):
    name: str

    def generate(self, prompt: str, context: str | None) -> ProviderResponse: ...
