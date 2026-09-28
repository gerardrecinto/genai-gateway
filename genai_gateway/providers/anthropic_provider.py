"""Real-provider adapter, same ModelProvider interface as MockProvider.

Not exercised anywhere in this project's test suite and no API key is
configured for it here — this demonstrates the adapter shape for a real
provider, not a verified integration. `anthropic` is intentionally not in
requirements.txt since nothing in this repo's tests or CI needs it;
install it yourself (`pip install anthropic`) before using this class.
"""

import os

from genai_gateway.providers.base import ProviderResponse, approximate_token_count


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, model: str = "claude-sonnet-5", api_key: str | None = None):
        self.model = model
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY not set. This provider has not been run "
                "against the real API in this portfolio project."
            )

    def generate(self, prompt: str, context: str | None) -> ProviderResponse:
        import anthropic  # lazy import: optional dependency, not in requirements.txt

        client = anthropic.Anthropic(api_key=self.api_key)
        full_prompt = f"Context:\n{context}\n\nQuestion:\n{prompt}" if context else prompt

        response = client.messages.create(
            model=self.model,
            max_tokens=1024,
            messages=[{"role": "user", "content": full_prompt}],
        )
        text = "".join(block.text for block in response.content if hasattr(block, "text"))

        return ProviderResponse(
            text=text,
            provider_name=self.name,
            prompt_tokens=getattr(response.usage, "input_tokens", approximate_token_count(full_prompt)),
            completion_tokens=getattr(response.usage, "output_tokens", approximate_token_count(text)),
        )
