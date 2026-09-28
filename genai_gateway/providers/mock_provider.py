"""Deterministic local model provider — no network calls, no API key,
usable in CI and this project's own test suite without paid API cost.
Not a stand-in for real model quality; it's here so the pipeline
(caching, rate limiting, response validation, escalation) can be exercised
end-to-end without depending on a paid provider being reachable.
"""

from genai_gateway.providers.base import ProviderResponse, approximate_token_count


class MockProvider:
    name = "mock"

    def generate(self, prompt: str, context: str | None) -> ProviderResponse:
        word_count = len(prompt.split())

        if word_count < 4:
            answer = (
                "I don't have enough context to answer this confidently "
                "could you provide more detail?"
            )
        else:
            topic = prompt.strip().rstrip("?")
            answer = f"Here is a synthesized answer addressing: {topic}."

        prefix = f"[using retrieved context: {context[:60]}] " if context else ""
        text = prefix + answer

        return ProviderResponse(
            text=text,
            provider_name=self.name,
            prompt_tokens=approximate_token_count(prompt),
            completion_tokens=approximate_token_count(text),
        )
