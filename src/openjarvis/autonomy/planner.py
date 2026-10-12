from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class PlanStep:
    id: str
    title: str
    objective: str
    verification: str


@dataclass(frozen=True, slots=True)
class AutonomyPlan:
    kind: str
    steps: tuple[PlanStep, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "steps": [asdict(step) for step in self.steps],
        }


_CODE_MARKERS = {
    "repo",
    "repository",
    "repositorio",
    "codigo",
    "código",
    "code",
    "branch",
    "rama",
    "commit",
    "pull request",
    "pr ",
    "pytest",
    "test",
    "pruebas",
    "build",
    "pipeline",
}
_DEPLOY_MARKERS = {
    "deploy",
    "deployment",
    "desplieg",
    "docker",
    "contenedor",
    "container",
    "produccion",
    "producción",
    "devops",
}
_DATA_MARKERS = {
    "power bi",
    "powerbi",
    "excel",
    "data",
    "datos",
    "sql",
    "reporte",
    "report",
    "dashboard",
    "modelo",
    "matrix",
    "matriz",
}


def build_autonomy_plan(goal: str) -> AutonomyPlan:
    normalized = " ".join(goal.lower().split())
    kind = _classify(normalized)

    steps: list[PlanStep] = [
        PlanStep(
            id="inspect",
            title="Inspect current state",
            objective="Collect real state, constraints, files, services and prior checkpoints.",
            verification="Current state is supported by tool evidence.",
        ),
        PlanStep(
            id="plan",
            title="Derive safe actions",
            objective="Translate the objective into bounded actions and dependencies.",
            verification="Actions cover the requested outcome without unrelated changes.",
        ),
    ]

    if kind == "code":
        steps.extend(
            [
                PlanStep(
                    id="implement",
                    title="Implement bounded change",
                    objective="Apply the smallest coherent code/configuration changes.",
                    verification="Only intended files changed and diff is internally consistent.",
                ),
                PlanStep(
                    id="test",
                    title="Run directed tests",
                    objective="Execute focused automated tests for the changed behavior.",
                    verification="Directed tests pass with real command output.",
                ),
                PlanStep(
                    id="quality",
                    title="Run quality gate",
                    objective="Check formatting, static issues, regression risk and diff hygiene.",
                    verification="Quality checks pass or every remaining issue is explicitly recorded.",
                ),
            ]
        )
    elif kind == "data":
        steps.extend(
            [
                PlanStep(
                    id="validate-data",
                    title="Validate source and model",
                    objective="Verify source totals, mappings, relationships, filters and temporal logic.",
                    verification="Control totals and requested business rules reconcile.",
                ),
                PlanStep(
                    id="apply",
                    title="Apply analytical changes",
                    objective="Implement the requested model/report/data changes.",
                    verification="Changed outputs reflect the intended business logic.",
                ),
            ]
        )
    else:
        steps.append(
            PlanStep(
                id="execute",
                title="Execute objective",
                objective="Perform the concrete actions required by the objective.",
                verification="Every material action has tool or system evidence.",
            )
        )

    if _contains_any(normalized, _DEPLOY_MARKERS):
        steps.append(
            PlanStep(
                id="deploy",
                title="Deploy and smoke test",
                objective="Deploy to the requested environment and verify service health.",
                verification="Deployment and smoke/health checks succeed.",
            )
        )

    steps.extend(
        [
            PlanStep(
                id="repair",
                title="Repair recoverable failures",
                objective="Retry or correct recoverable failures without broadening scope.",
                verification="Retries converge or the task is blocked with a concrete reason.",
            ),
            PlanStep(
                id="complete",
                title="Verify completion",
                objective="Confirm the user objective is fully satisfied and record evidence.",
                verification="Completion criteria are met before AUTONOMY_DONE is emitted.",
            ),
        ]
    )
    return AutonomyPlan(kind=kind, steps=tuple(steps))


def _classify(normalized: str) -> str:
    if _contains_any(normalized, _CODE_MARKERS):
        return "code"
    if _contains_any(normalized, _DATA_MARKERS):
        return "data"
    return "general"


def _contains_any(text: str, markers: set[str]) -> bool:
    return any(marker in text for marker in markers)
