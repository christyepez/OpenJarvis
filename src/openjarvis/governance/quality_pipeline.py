"""Quality-gate planning for implementation and multimodal work."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class QualityStage(str, Enum):
    BUILD_TESTS = "build-tests"
    MULTIMODAL_REVIEW = "multimodal-review"
    ANTI_SLOP = "anti-slop"
    THERMOS = "thermos"
    RELEASE = "release"


@dataclass(frozen=True, slots=True)
class QualityPlan:
    """Ordered quality stages for one implementation."""

    stages: tuple[QualityStage, ...]


class QualityPipelinePlanner:
    """Build evidence-oriented quality plans from task characteristics."""

    def plan(
        self,
        *,
        has_code_changes: bool = True,
        has_visual_changes: bool = False,
        material_change: bool = True,
        release_candidate: bool = False,
    ) -> QualityPlan:
        stages: list[QualityStage] = []
        if has_code_changes:
            stages.append(QualityStage.BUILD_TESTS)

        if has_visual_changes:
            stages.append(QualityStage.MULTIMODAL_REVIEW)

        if has_code_changes or has_visual_changes:
            stages.append(QualityStage.ANTI_SLOP)

        if material_change or release_candidate:
            stages.append(QualityStage.THERMOS)

        if release_candidate:
            stages.append(QualityStage.RELEASE)

        return QualityPlan(stages=tuple(stages))


__all__ = [
    "QualityPlan",
    "QualityPipelinePlanner",
    "QualityStage",
]
