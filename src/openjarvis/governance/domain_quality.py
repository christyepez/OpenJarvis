"""Quality policy for bounded non-project domain tasks."""

from __future__ import annotations

from dataclasses import dataclass

from openjarvis.governance.quality_pipeline import QualityStage


@dataclass(frozen=True, slots=True)
class DomainQualityPlan:
    """Quality requirements for one non-project task."""

    required: bool
    stages: tuple[QualityStage, ...]
    reason: str


class DomainQualityPlanner:
    """Choose proportional quality gates without turning work into a project."""

    def plan(
        self,
        *,
        capability: str,
        domain: str = "general",
        quality_mode: str = "auto",
    ) -> DomainQualityPlan:
        mode = (quality_mode or "auto").strip().casefold()
        normalized_capability = (capability or "general").strip().casefold()
        normalized_domain = (domain or "general").strip().casefold()

        if mode == "none":
            return DomainQualityPlan(False, (), "Quality explicitly disabled.")

        if normalized_capability == "multimodal":
            return DomainQualityPlan(
                True,
                (
                    QualityStage.MULTIMODAL_REVIEW,
                    QualityStage.ANTI_SLOP,
                    QualityStage.THERMOS,
                ),
                "Visual or multimodal work requires visual and quality review.",
            )

        if normalized_capability == "coding":
            return DomainQualityPlan(
                True,
                (
                    QualityStage.ANTI_SLOP,
                    QualityStage.THERMOS,
                ),
                "Coding work requires code-quality review.",
            )

        if mode == "required":
            return DomainQualityPlan(
                True,
                (QualityStage.THERMOS,),
                "Quality explicitly required for this task.",
            )

        return DomainQualityPlan(
            False,
            (),
            (
                "Simple bounded non-project work does not require quality gates "
                f"(domain={normalized_domain})."
            ),
        )


__all__ = ["DomainQualityPlan", "DomainQualityPlanner"]
