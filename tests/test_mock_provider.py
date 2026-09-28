from genai_gateway.providers.mock_provider import MockProvider


def test_short_prompt_produces_hedging_response():
    response = MockProvider().generate("why", None)
    assert "don't have enough context" in response.text


def test_normal_prompt_produces_answer():
    response = MockProvider().generate("How do I roll back a deployment safely?", None)
    assert "synthesized answer" in response.text
    assert response.provider_name == "mock"


def test_context_is_prefixed_when_present():
    response = MockProvider().generate("How do I roll back a deployment safely?", "some retrieved context")
    assert response.text.startswith("[using retrieved context:")


def test_token_counts_are_positive():
    response = MockProvider().generate("How do I roll back a deployment safely?", None)
    assert response.prompt_tokens > 0
    assert response.completion_tokens > 0
