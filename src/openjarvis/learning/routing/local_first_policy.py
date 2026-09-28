"""Local-first model routing policy.

This policy reuses the existing heuristic router but constrains its candidate
set to local models whenever at least one local model is available.
"""

from __future__ import annotations

from typing import List

from openjarvis.core.registry import ModelRegistry, RouterPolicyRegistry
from openjarvis.core.types import RoutingContext
from openjarvis.learning._stubs import RouterPolicy
from openjarvis.learning.routing.router import HeuristicRouter


def _is_local_model(model_id: str) -> bool:
    """Return True when a registered model has a non-cloud execution engine."""
    try:
        spec = ModelRegistry.get(model_id)
    except KeyError:
        return False
    engines = tuple(getattr(spec, "supported_engines", ()) or ())
    return any(engine != "cloud" for engine in engines)
class LocalFirstRouter(RouterPolicy):
    """Prefer local models and delegate final ranking to HeuristicRouter."""

    def __init__(
        self,
        available_models: List[str] | None = None,
        *,
        default_model: str = "",
        fallback_model: str = "",
    ) -> None:
        self._available = available_models or []
        self._default = default_model
        self._fallback = fallback_model

    @property
    def available_models(self) -> List[str]:
        return list(self._available)

    def select_model(self, context: RoutingContext) -> str:
        available = self._available or list(ModelRegistry.keys())
        if not available:
            return self._default or self._fallback or ""

        local = [model for model in available if _is_local_model(model)]
        candidates = local or available
        router = HeuristicRouter(
            available_models=candidates,
            default_model=self._default,
            fallback_model=self._fallback,
        )
        return router.select_model(context)
def ensure_registered() -> None:
    """Register the local-first policy when not already present."""
    if not RouterPolicyRegistry.contains("local-first"):
        RouterPolicyRegistry.register_value("local-first", LocalFirstRouter)


ensure_registered()


__all__ = ["LocalFirstRouter", "ensure_registered"]
