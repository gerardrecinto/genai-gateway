from genai_gateway.retrieval.knowledge_base import match_knowledge_base


def test_strong_phrase_resolves_without_model():
    match = match_knowledge_base("kubectl rollout undo deployment/api, what does that do?")
    assert match.decision == "resolve"
    assert match.topic == "k8s_rollback"


def test_weak_keyword_enriches_but_does_not_resolve():
    match = match_knowledge_base("my deployment stuck rollout is taking forever, why?")
    assert match.decision == "enrich"
    assert match.topic == "k8s_rollback"


def test_no_match_returns_none():
    match = match_knowledge_base("what's a good recipe for banana bread?")
    assert match.decision is None
