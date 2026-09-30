"""JarvisBench: lightweight evaluation records for governed agent execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from statistics import mean
from typing import Iterable, Sequence

from openjarvis.core.types import ModelSpec


@dataclass(frozen=True, slots=True)
class JarvisBenchRoutingCase:
    """Expected domain/capability/model route for one benchmark query."""

    task_id: str
    query: str
    expected_domain: str
    expected_capability: str
    expected_model: str


@dataclass(frozen=True, slots=True)
class JarvisBenchSample:
    """One evaluated agent task."""

    task_id: str
    success: bool
    expected_model: str = ""
    selected_model: str = ""
    expected_tools: frozenset[str] = frozenset()
    selected_tools: frozenset[str] = frozenset()
    expected_domain: str = ""
    selected_domain: str = ""
    expected_capability: str = ""
    selected_capability: str = ""
    policy_violations: int = 0
    latency_seconds: float = 0.0
    cost_usd: float = 0.0
    retries: int = 0
    metadata: dict[str, object] = field(default_factory=dict)
@dataclass(frozen=True, slots=True)
class JarvisBenchSummary:
    samples: int
    task_success_rate: float
    model_routing_accuracy: float
    tool_selection_accuracy: float
    domain_routing_accuracy: float
    capability_routing_accuracy: float
    policy_violation_rate: float
    average_latency_seconds: float
    average_cost_usd: float
    average_retries: float


def _safe_mean(values: Iterable[float]) -> float:
    items = list(values)
    return mean(items) if items else 0.0


def evaluate_routing_cases(
    cases: Iterable[JarvisBenchRoutingCase],
    *,
    runtime_model_ids: Sequence[str],
    catalog: Iterable[ModelSpec],
    preferred_models: Sequence[str] = (),
) -> list[JarvisBenchSample]:
    """Evaluate current multidomain and capability routing on benchmark cases."""
    from openjarvis.governance.execution_router import (
        classify_task_capability,
        recommend_installed_model,
    )
    from openjarvis.memory.context_router import ContextRouter

    catalog_rows = list(catalog)
    samples: list[JarvisBenchSample] = []
    for case in cases:
        selected_domain = ContextRouter().route(case.query).primary.value
        selected_capability = classify_task_capability(case.query)
        selected_model = (
            recommend_installed_model(
                runtime_model_ids,
                catalog_rows,
                capability=selected_capability,
                preferred_models=preferred_models,
            )
            or ""
        )
        success = (
            selected_domain == case.expected_domain
            and selected_capability == case.expected_capability
            and selected_model == case.expected_model
        )
        samples.append(
            JarvisBenchSample(
                task_id=case.task_id,
                success=success,
                expected_model=case.expected_model,
                selected_model=selected_model,
                expected_domain=case.expected_domain,
                selected_domain=selected_domain,
                expected_capability=case.expected_capability,
                selected_capability=selected_capability,
            )
        )
    return samples


def summarize(samples: Iterable[JarvisBenchSample]) -> JarvisBenchSummary:
    """Aggregate core TaskBench-inspired metrics."""
    rows = list(samples)
    if not rows:
        return JarvisBenchSummary(
            0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
        )

    model_rows = [row for row in rows if row.expected_model]
    tool_rows = [row for row in rows if row.expected_tools]
    domain_rows = [row for row in rows if row.expected_domain]
    capability_rows = [row for row in rows if row.expected_capability]
    model_accuracy = _safe_mean(
        1.0 if row.selected_model == row.expected_model else 0.0
        for row in model_rows
    )
    tool_accuracy = _safe_mean(
        len(row.expected_tools & row.selected_tools) / len(row.expected_tools)
        for row in tool_rows
    )

    return JarvisBenchSummary(
        samples=len(rows),
        task_success_rate=_safe_mean(1.0 if row.success else 0.0 for row in rows),
        model_routing_accuracy=model_accuracy,
        tool_selection_accuracy=tool_accuracy,
        domain_routing_accuracy=_safe_mean(
            1.0 if row.selected_domain == row.expected_domain else 0.0
            for row in domain_rows
        ),
        capability_routing_accuracy=_safe_mean(
            1.0 if row.selected_capability == row.expected_capability else 0.0
            for row in capability_rows
        ),
        policy_violation_rate=_safe_mean(
            1.0 if row.policy_violations else 0.0 for row in rows
        ),
        average_latency_seconds=_safe_mean(row.latency_seconds for row in rows),
        average_cost_usd=_safe_mean(row.cost_usd for row in rows),
        average_retries=_safe_mean(float(row.retries) for row in rows),
    )


__all__ = [
    "JarvisBenchRoutingCase",
    "JarvisBenchSample",
    "JarvisBenchSummary",
    "evaluate_routing_cases",
    "summarize",
]
