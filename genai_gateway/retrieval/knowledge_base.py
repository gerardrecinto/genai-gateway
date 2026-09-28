"""Structured context enrichment: a small hand-authored runbook KB, not a
vector store. Deliberately simple — the point is demonstrating the
retrieval-before-model pattern and a resolve/enrich distinction, not
building a RAG system. A strong match answers directly, RAIL-style,
without a model call; a weak match attaches context but still defers to
the model.
"""

from dataclasses import dataclass, field


@dataclass
class KBEntry:
    topic: str
    strong_phrases: list[str]  # exact-ish match -> resolve without a model call
    weak_keywords: list[str]  # loose overlap -> enrich context, still call model
    answer: str


KNOWLEDGE_BASE: list[KBEntry] = [
    KBEntry(
        topic="k8s_rollback",
        strong_phrases=["kubectl rollout undo", "how do i roll back a kubernetes deployment"],
        weak_keywords=["rollback", "rollout", "deployment stuck"],
        answer=(
            "Roll back a Kubernetes deployment with `kubectl rollout undo "
            "deployment/<name>`. Check progress with `kubectl rollout status "
            "deployment/<name>`. If `progressDeadlineSeconds` is set, a stuck "
            "rollout is marked Progressing=False automatically once that "
            "window elapses, which is what should trigger the undo."
        ),
    ),
    KBEntry(
        topic="kafka_consumer_lag",
        strong_phrases=["what causes kafka consumer lag", "kafka partition imbalance"],
        weak_keywords=["consumer lag", "kafka rebalance", "offset lag"],
        answer=(
            "Consumer lag usually means partitions are processed unevenly "
            "across the group. Check partition-to-consumer assignment first "
            "with `kafka-consumer-groups.sh --describe`; a skewed assignment "
            "(few consumers handling most partitions) is the most common root "
            "cause, not consumer throughput alone."
        ),
    ),
    KBEntry(
        topic="terraform_state_lock",
        strong_phrases=["terraform state is locked", "terraform state lock error"],
        weak_keywords=["state lock", "terraform locked"],
        answer=(
            "A stuck Terraform state lock (DynamoDB backend) can be released "
            "with `terraform force-unlock <lock-id>` — only do this after "
            "confirming no other `apply` is actually in progress, since force-"
            "unlocking during a real concurrent apply corrupts state."
        ),
    ),
]


@dataclass
class KBMatch:
    decision: str | None  # "resolve" | "enrich" | None
    topic: str | None = None
    text: str | None = None
    matched_keywords: list[str] = field(default_factory=list)


def match_knowledge_base(prompt: str) -> KBMatch:
    lowered = prompt.lower()

    for entry in KNOWLEDGE_BASE:
        for phrase in entry.strong_phrases:
            if phrase in lowered:
                return KBMatch(decision="resolve", topic=entry.topic, text=entry.answer, matched_keywords=[phrase])

    for entry in KNOWLEDGE_BASE:
        matched = [kw for kw in entry.weak_keywords if kw in lowered]
        if matched:
            return KBMatch(decision="enrich", topic=entry.topic, text=entry.answer, matched_keywords=matched)

    return KBMatch(decision=None)
