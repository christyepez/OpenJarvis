from openjarvis.governance import (
    CapabilityAssessment,
    CapabilityDecision,
    CapabilityDecisionEngine,
)


def test_capability_decision_prefers_reuse() -> None:
    result = CapabilityDecisionEngine().decide(
        CapabilityAssessment(
            "authentication",
            reusable_exists=True,
            can_extend=True,
            evidence="Portal already exposes authentication.",
        )
    )

    assert result.decision is CapabilityDecision.REUSE


def test_capability_decision_blocks_unresolved_dependency_first() -> None:
    result = CapabilityDecisionEngine().decide(
        CapabilityAssessment(
            "payments",
            reusable_exists=True,
            dependency_blocked=True,
        )
    )

    assert result.decision is CapabilityDecision.BLOCKED
def test_capability_decision_extends_then_adapts_then_creates() -> None:
    engine = CapabilityDecisionEngine()

    extend = engine.decide(CapabilityAssessment("menus", can_extend=True))
    adapt = engine.decide(CapabilityAssessment("external-api", can_adapt=True))
    create = engine.decide(CapabilityAssessment("new-domain-capability"))

    assert extend.decision is CapabilityDecision.EXTEND
    assert adapt.decision is CapabilityDecision.ADAPT
    assert create.decision is CapabilityDecision.CREATE
