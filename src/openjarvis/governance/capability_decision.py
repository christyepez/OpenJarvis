"""Structured REUSE/EXTEND/ADAPT/CREATE/BLOCKED capability decisions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class CapabilityDecision(str, Enum):
    REUSE = "REUSE"
    EXTEND = "EXTEND"
    ADAPT = "ADAPT"
    CREATE = "CREATE"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True, slots=True)
class CapabilityAssessment:
    """Facts known before deciding whether to create a capability."""

    capability: str
    reusable_exists: bool = False
    can_extend: bool = False
    can_adapt: bool = False
    dependency_blocked: bool = False
    evidence: str = ""


@dataclass(frozen=True, slots=True)
class CapabilityResolution:
    decision: CapabilityDecision
    capability: str
    reason: str
    evidence: str = ""


class CapabilityDecisionEngine:
    """Apply the common no-duplication decision order."""

    def decide(self, assessment: CapabilityAssessment) -> CapabilityResolution:
        if assessment.dependency_blocked:
            return CapabilityResolution(
                CapabilityDecision.BLOCKED,
                assessment.capability,
                "A required dependency or contract is unresolved.",
                assessment.evidence,
            )
        if assessment.reusable_exists:
            return CapabilityResolution(
                CapabilityDecision.REUSE,
                assessment.capability,
                "An existing compatible capability should be reused.",
                assessment.evidence,
            )
        if assessment.can_extend:
            return CapabilityResolution(
                CapabilityDecision.EXTEND,
                assessment.capability,
                "Existing platform capability can be extended safely.",
                assessment.evidence,
            )
        if assessment.can_adapt:
            return CapabilityResolution(
                CapabilityDecision.ADAPT,
                assessment.capability,
                "Use an adapter around an existing external or shared capability.",
                assessment.evidence,
            )
        return CapabilityResolution(
            CapabilityDecision.CREATE,
            assessment.capability,
            "No reusable, extensible, or adaptable capability was identified.",
            assessment.evidence,
        )


__all__ = [
    "CapabilityAssessment",
    "CapabilityDecision",
    "CapabilityDecisionEngine",
    "CapabilityResolution",
]
