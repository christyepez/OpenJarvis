"""Cost governance for model, tool, connector, and execution providers.

The policy is deliberately conservative: local and free options are preferred;
Codex and Commander are pre-approved paid providers; any other paid provider
requires explicit user approval before execution.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable


class CostClass(str, Enum):
    """Normalized provider cost classification."""

    LOCAL = "local"
    FREE = "free"
    APPROVED_PAID = "approved_paid"
    REQUIRES_APPROVAL = "requires_approval"


@dataclass(frozen=True, slots=True)
class ProviderDescriptor:
    """Metadata used to decide whether a provider may execute."""

    name: str
    cost_class: CostClass
    local: bool = False
    free: bool = False
    capabilities: frozenset[str] = field(default_factory=frozenset)

    @property
    def normalized_name(self) -> str:
        return self.name.strip().lower()


@dataclass(frozen=True, slots=True)
class CostDecision:
    """Result returned by :class:`CostPolicy`."""

    allowed: bool
    reason: str
    requires_user_approval: bool = False


class CostPolicy:
    """Apply the user's local-first, free-first provider policy."""

    DEFAULT_APPROVED_PAID = frozenset(
        {"codex", "openai-codex", "commander", "remote desktop commander"}
    )

    def __init__(self, approved_paid: Iterable[str] | None = None) -> None:
        approved = approved_paid or self.DEFAULT_APPROVED_PAID
        self._approved_paid = frozenset(name.strip().lower() for name in approved)

    @classmethod
    def from_config(cls, governance_config: object) -> "CostPolicy":
        raw = str(getattr(governance_config, "approved_paid", "") or "")
        approved = [part.strip() for part in raw.split(",") if part.strip()]
        return cls(approved_paid=approved or None)

    @property
    def approved_paid(self) -> frozenset[str]:
        return self._approved_paid

    def classify(self, provider: ProviderDescriptor) -> CostClass:
        """Normalize a provider against the configured allow-list."""
        if provider.local or provider.cost_class is CostClass.LOCAL:
            return CostClass.LOCAL
        if provider.free or provider.cost_class is CostClass.FREE:
            return CostClass.FREE
        normalized_name = provider.normalized_name
        aliases = {"openai-codex": "codex"}
        canonical_name = aliases.get(normalized_name, normalized_name)
        if (
            normalized_name in self._approved_paid
            or canonical_name in self._approved_paid
        ):
            return CostClass.APPROVED_PAID
        return CostClass.REQUIRES_APPROVAL

    def decide(
        self, provider: ProviderDescriptor, *, user_approved: bool = False
    ) -> CostDecision:
        """Return whether the provider may be used for this execution."""
        cost_class = self.classify(provider)
        if cost_class is CostClass.LOCAL:
            return CostDecision(True, "local provider preferred")
        if cost_class is CostClass.FREE:
            return CostDecision(True, "free provider allowed")
        if cost_class is CostClass.APPROVED_PAID:
            return CostDecision(True, "provider is pre-approved")
        if user_approved:
            return CostDecision(True, "paid provider explicitly approved by user")
        return CostDecision(
            False,
            "paid provider requires explicit user approval",
            requires_user_approval=True,
        )

    def rank(self, providers: Iterable[ProviderDescriptor]) -> list[ProviderDescriptor]:
        """Order candidates local -> free -> approved paid -> approval required."""
        priority = {
            CostClass.LOCAL: 0,
            CostClass.FREE: 1,
            CostClass.APPROVED_PAID: 2,
            CostClass.REQUIRES_APPROVAL: 3,
        }
        return sorted(
            providers,
            key=lambda item: (priority[self.classify(item)], item.name.lower()),
        )
