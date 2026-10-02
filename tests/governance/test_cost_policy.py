from openjarvis.governance.cost_policy import (
    CostClass,
    CostPolicy,
    ProviderDescriptor,
)


def provider(name: str, cost: CostClass, **kwargs) -> ProviderDescriptor:
    return ProviderDescriptor(name=name, cost_class=cost, **kwargs)


def test_local_and_free_providers_are_allowed() -> None:
    policy = CostPolicy()

    assert policy.decide(provider("ollama", CostClass.LOCAL)).allowed
    assert policy.decide(provider("community-api", CostClass.FREE)).allowed


def test_codex_and_commander_are_preapproved() -> None:
    policy = CostPolicy()

    assert policy.decide(provider("Codex", CostClass.REQUIRES_APPROVAL)).allowed
    assert policy.decide(provider("Commander", CostClass.REQUIRES_APPROVAL)).allowed


def test_other_paid_provider_requires_explicit_approval() -> None:
    policy = CostPolicy()
    candidate = provider("commercial-model-x", CostClass.REQUIRES_APPROVAL)

    decision = policy.decide(candidate)
    assert decision.allowed is False
    assert decision.requires_user_approval is True

    approved = policy.decide(candidate, user_approved=True)
    assert approved.allowed is True
    assert approved.requires_user_approval is False


def test_rank_prefers_local_then_free_then_preapproved_paid() -> None:
    policy = CostPolicy()
    candidates = [
        provider("paid-x", CostClass.REQUIRES_APPROVAL),
        provider("Codex", CostClass.REQUIRES_APPROVAL),
        provider("free-x", CostClass.FREE),
        provider("ollama", CostClass.LOCAL),
    ]

    ranked = policy.rank(candidates)
    assert [item.name for item in ranked] == ["ollama", "free-x", "Codex", "paid-x"]
