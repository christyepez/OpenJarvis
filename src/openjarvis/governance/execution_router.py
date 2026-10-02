"""Cross-engine model routing with local/free-first cost governance."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

from openjarvis.core.config import HardwareInfo
from openjarvis.core.types import ModelSpec
from openjarvis.governance.cost_policy import CostClass, CostPolicy, ProviderDescriptor
from openjarvis.governance.model_selection import estimated_model_memory_gb

_NORMALIZE_RE = re.compile(r"[^a-z0-9]+")
_CODE_HINTS = (
    "python",
    "typescript",
    "javascript",
    "csharp",
    "c#",
    ".net",
    "sql",
    "refactor",
    "unit test",
    "pytest",
    "source code",
    "codigo",
    "código",
)
_VISUAL_HINTS = (
    "image",
    "screenshot",
    "diagram",
    "dashboard",
    "photo",
    "picture",
    "visual",
    "imagen",
    "captura",
    "diagrama",
    "panel",
    "grafico",
    "gráfico",
)


def _normalized(value: str) -> str:
    return _NORMALIZE_RE.sub("", value.casefold())


def match_catalog_model(
    runtime_model_id: str,
    models: Iterable[ModelSpec],
) -> ModelSpec | None:
    """Resolve a runtime model identifier to the closest catalog entry."""
    runtime_norm = _normalized(runtime_model_id)
    exact: list[ModelSpec] = []
    fuzzy: list[tuple[int, ModelSpec]] = []

    for spec in models:
        if spec.model_id.casefold() == runtime_model_id.casefold():
            exact.append(spec)
            continue

        aliases = list(spec.metadata.get("runtime_aliases", ()) or ())
        hf_repo = spec.metadata.get("hf_repo")
        if isinstance(hf_repo, str) and hf_repo:
            aliases.append(hf_repo)
        aliases.append(spec.name)

        for alias in aliases:
            alias_norm = _normalized(str(alias))
            if not alias_norm:
                continue
            if alias_norm == runtime_norm:
                return spec
            if alias_norm in runtime_norm or runtime_norm in alias_norm:
                fuzzy.append((len(alias_norm), spec))

    if exact:
        return exact[0]
    if fuzzy:
        fuzzy.sort(key=lambda item: -item[0])
        return fuzzy[0][1]
    return None


@dataclass(frozen=True, slots=True)
class EngineModelCandidate:
    """One model that is currently routable through one engine."""

    engine: str
    runtime_model_id: str
    spec: ModelSpec | None
    is_local: bool
    cost_class: CostClass
    estimated_memory_gb: float = 0.0

    @property
    def catalog_model_id(self) -> str:
        return self.spec.model_id if self.spec is not None else self.runtime_model_id


@dataclass(frozen=True, slots=True)
class EngineModelRoute:
    """Selected engine/model pair."""

    engine: str
    model: str
    runtime_model_id: str
    reason: str
    cost_class: CostClass


class EngineModelRouter:
    """Select an engine/model pair while enforcing cost and hardware policy."""

    def __init__(self, cost_policy: CostPolicy | None = None) -> None:
        self._cost_policy = cost_policy or CostPolicy()

    @staticmethod
    def _preference_rank(model_id: str, preferred_models: Sequence[str]) -> int:
        model_norm = _normalized(model_id)
        for index, preferred in enumerate(preferred_models):
            pref_norm = _normalized(preferred)
            if pref_norm and (
                model_norm == pref_norm
                or pref_norm in model_norm
                or model_norm in pref_norm
            ):
                return index
        return len(preferred_models)

    @staticmethod
    def _capability_rank(spec: ModelSpec | None, capability: str) -> int:
        if not capability or capability in {"general", "reasoning"}:
            return 0
        if spec is None:
            return 2

        normalized = capability.casefold().strip()
        metadata = spec.metadata or {}
        specialization = str(metadata.get("specialization", "")).casefold()
        model_text = f"{spec.model_id} {spec.name}".casefold()
        modalities = {
            str(value).casefold() for value in (metadata.get("modalities", ()) or ())
        }

        if normalized in {"coding", "code"}:
            return 0 if specialization == "coding" or "code" in model_text else 1
        if normalized in {"multimodal", "vision", "visual", "image"}:
            return 0 if "image" in modalities else 1
        return 1

    def candidates(
        self,
        *,
        models_by_engine: Mapping[str, Sequence[str]],
        catalog: Iterable[ModelSpec],
        hardware: HardwareInfo,
        preferred_models: Sequence[str] = (),
        capability: str = "",
    ) -> list[EngineModelCandidate]:
        """Build cost-aware candidates from currently available engines."""
        catalog_rows = list(catalog)
        available_ram = max((hardware.ram_gb - 4.0) * 0.8, 0.0)
        if hardware.gpu and hardware.gpu.vram_gb > 0:
            available_ram = max(
                available_ram,
                hardware.gpu.vram_gb * max(hardware.gpu.count, 1) * 0.9,
            )

        candidates: list[EngineModelCandidate] = []
        for engine, runtime_ids in models_by_engine.items():
            is_local = engine != "cloud"
            for runtime_id in runtime_ids:
                spec = match_catalog_model(runtime_id, catalog_rows)
                estimated = estimated_model_memory_gb(spec) if spec else 0.0

                if is_local and spec is not None and estimated > available_ram:
                    continue

                provider_name = (
                    spec.provider
                    if spec is not None and spec.provider
                    else ("local" if is_local else engine)
                )
                if is_local:
                    cost_class = CostClass.LOCAL
                else:
                    descriptor = ProviderDescriptor(
                        name=provider_name,
                        cost_class=CostClass.REQUIRES_APPROVAL,
                    )
                    cost_class = self._cost_policy.classify(descriptor)

                candidates.append(
                    EngineModelCandidate(
                        engine=engine,
                        runtime_model_id=runtime_id,
                        spec=spec,
                        is_local=is_local,
                        cost_class=cost_class,
                        estimated_memory_gb=estimated,
                    )
                )

        priority = {
            CostClass.LOCAL: 0,
            CostClass.FREE: 1,
            CostClass.APPROVED_PAID: 2,
            CostClass.REQUIRES_APPROVAL: 3,
        }
        candidates.sort(
            key=lambda item: (
                priority[item.cost_class],
                self._capability_rank(item.spec, capability),
                self._preference_rank(item.catalog_model_id, preferred_models),
                -float(
                    getattr(item.spec, "active_parameter_count_b", 0.0)
                    or getattr(item.spec, "parameter_count_b", 0.0)
                    or 0.0
                ),
                item.engine,
                item.runtime_model_id.casefold(),
            )
        )
        return candidates

    def route(
        self,
        *,
        models_by_engine: Mapping[str, Sequence[str]],
        catalog: Iterable[ModelSpec],
        hardware: HardwareInfo,
        preferred_models: Sequence[str] = (),
        user_approved_paid: Sequence[str] = (),
        capability: str = "",
    ) -> EngineModelRoute | None:
        """Choose the first allowed candidate, never auto-using new paid services."""
        approvals = {name.casefold() for name in user_approved_paid}
        for candidate in self.candidates(
            models_by_engine=models_by_engine,
            catalog=catalog,
            hardware=hardware,
            preferred_models=preferred_models,
            capability=capability,
        ):
            if candidate.cost_class is CostClass.REQUIRES_APPROVAL:
                provider = (
                    candidate.spec.provider
                    if candidate.spec is not None
                    else candidate.engine
                )
                if provider.casefold() not in approvals:
                    continue
            reason = (
                "local/free-first route"
                if candidate.is_local
                else "approved provider route"
            )
            if capability:
                reason = f"{reason}; capability={capability}"
            return EngineModelRoute(
                engine=candidate.engine,
                model=candidate.catalog_model_id,
                runtime_model_id=candidate.runtime_model_id,
                reason=reason,
                cost_class=candidate.cost_class,
            )
        return None


def classify_task_capability(
    query: str,
    *,
    has_visual_input: bool = False,
) -> str:
    """Classify one request into a local worker capability."""
    if has_visual_input:
        return "multimodal"

    normalized = query.casefold()
    if any(hint in normalized for hint in _VISUAL_HINTS):
        return "multimodal"

    from openjarvis.learning.routing.router import build_routing_context

    context = build_routing_context(query)
    if context.has_code or any(hint in normalized for hint in _CODE_HINTS):
        return "coding"
    return "general"


def local_runtime_models(engine: Any) -> list[str]:
    """Return models exposed by local engines only."""
    if engine is None:
        return []

    grouped = getattr(engine, "models_by_engine", None)
    if callable(grouped):
        try:
            groups = grouped()
        except Exception:
            groups = None
        if isinstance(groups, Mapping):
            rows: list[str] = []
            for key, values in groups.items():
                if str(key).casefold() == "cloud":
                    continue
                rows.extend(str(value) for value in (values or []))
            return sorted(set(rows))

    engine_id = str(getattr(engine, "engine_id", "") or "").casefold()
    if engine_id == "cloud":
        return []

    try:
        return sorted(set(str(value) for value in (engine.list_models() or [])))
    except Exception:
        return []


def recommend_model_for_task(
    engine: Any,
    query: str,
    catalog: Iterable[ModelSpec],
    *,
    preferred_models: Sequence[str] = (),
    has_visual_input: bool = False,
) -> tuple[str | None, str]:
    """Select an installed local worker for a task without paid fallback."""
    capability = classify_task_capability(
        query,
        has_visual_input=has_visual_input,
    )
    model = recommend_installed_model(
        local_runtime_models(engine),
        catalog,
        capability=capability,
        preferred_models=preferred_models,
    )
    return model, capability


def recommend_installed_model(
    runtime_model_ids: Sequence[str],
    catalog: Iterable[ModelSpec],
    *,
    capability: str = "general",
    preferred_models: Sequence[str] = (),
) -> str | None:
    """Choose the best already-installed model for one task capability."""
    catalog_rows = list(catalog)
    router = EngineModelRouter()
    ranked: list[tuple[int, int, float, str]] = []

    for runtime_id in runtime_model_ids:
        spec = match_catalog_model(runtime_id, catalog_rows)
        capability_rank = router._capability_rank(spec, capability)
        preference_rank = router._preference_rank(
            spec.model_id if spec is not None else runtime_id,
            preferred_models,
        )
        strength = float(
            getattr(spec, "active_parameter_count_b", 0.0)
            or getattr(spec, "parameter_count_b", 0.0)
            or 0.0
        )
        ranked.append(
            (
                capability_rank,
                preference_rank,
                -strength,
                runtime_id,
            )
        )

    if not ranked:
        return None
    ranked.sort()
    return ranked[0][3]


__all__ = [
    "EngineModelCandidate",
    "EngineModelRoute",
    "EngineModelRouter",
    "classify_task_capability",
    "local_runtime_models",
    "match_catalog_model",
    "recommend_installed_model",
    "recommend_model_for_task",
]
