"""JarvisBench: lightweight evaluation records for governed agent execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from statistics import mean
from typing import Iterable


@dataclass(frozen=True, slots=True)
class JarvisBenchSample:
    """One evaluated agent task."""

    task_id: str
    success: bool
    expected_model: str = ""
    selected_model: str = ""
    expected_tools: frozenset[str] = frozenset()
    selected_tools: frozenset[str] = frozenset()
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
    policy_violation_rate: float
    average_latency_seconds: float
    average_cost_usd: float
    average_retries: float


def _safe_mean(values: Iterable[float]) -> float:
    items = list(values)
    return mean(items) if items else 0.0


def summarize(samples: Iterable[JarvisBenchSample]) -> JarvisBenchSummary:
    """Aggregate core TaskBench-inspired metrics."""
    rows = list(samples)
    if not rows:
        return JarvisBenchSummary(0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

    model_rows = [row for row in rows if row.expected_model]
    tool_rows = [row for row in rows if row.expected_tools]
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
        policy_violation_rate=_safe_mean(
            1.0 if row.policy_violations else 0.0 for row in rows
        ),
        average_latency_seconds=_safe_mean(row.latency_seconds for row in rows),
        average_cost_usd=_safe_mean(row.cost_usd for row in rows),
        average_retries=_safe_mean(float(row.retries) for row in rows),
    )


__all__ = ["JarvisBenchSample", "JarvisBenchSummary", "summarize"]
