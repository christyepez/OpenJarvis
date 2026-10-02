"""Tool-call guard that applies provider cost policy before execution."""

from __future__ import annotations

from collections.abc import Mapping

from openjarvis.governance.cost_policy import CostPolicy, ProviderDescriptor


class ProviderPolicyGuard:
    """Callable compatible with the OrchestratorAgent tool guard hook."""

    def __init__(
        self,
        policy: CostPolicy,
        tool_providers: Mapping[str, ProviderDescriptor] | None = None,
    ) -> None:
        self._policy = policy
        self._tool_providers = dict(tool_providers or {})
        self._request_approvals: set[str] = set()

    def register(self, tool_name: str, provider: ProviderDescriptor) -> None:
        self._tool_providers[tool_name] = provider

    def approve_for_request(self, provider_name: str) -> None:
        """Allow one otherwise-blocked paid provider for the active request."""
        self._request_approvals.add(provider_name.strip().lower())

    def clear_request_approvals(self) -> None:
        self._request_approvals.clear()

    def __call__(self, tool_name: str, tool_args: dict[str, object]) -> bool:
        """Return False only for a known provider that violates cost policy."""
        del tool_args  # reserved for future per-call provider resolution
        provider = self._tool_providers.get(tool_name)
        if provider is None:
            return True

        approved = provider.normalized_name in self._request_approvals
        return self._policy.decide(provider, user_approved=approved).allowed
