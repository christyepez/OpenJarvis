from openjarvis.governance.domain_quality import DomainQualityPlanner
from openjarvis.governance.quality_pipeline import QualityStage


def test_simple_general_task_skips_quality_by_default() -> None:
    plan = DomainQualityPlanner().plan(
        capability="general",
        domain="personal",
    )

    assert plan.required is False
    assert plan.stages == ()


def test_coding_task_gets_code_quality_review() -> None:
    plan = DomainQualityPlanner().plan(
        capability="coding",
        domain="professional",
    )

    assert plan.required is True
    assert plan.stages == (
        QualityStage.ANTI_SLOP,
        QualityStage.THERMOS,
    )


def test_multimodal_task_gets_visual_and_quality_review() -> None:
    plan = DomainQualityPlanner().plan(
        capability="multimodal",
        domain="knowledge",
    )

    assert plan.required is True
    assert plan.stages == (
        QualityStage.MULTIMODAL_REVIEW,
        QualityStage.ANTI_SLOP,
        QualityStage.THERMOS,
    )


def test_quality_mode_none_disables_quality() -> None:
    plan = DomainQualityPlanner().plan(
        capability="coding",
        quality_mode="none",
    )

    assert plan.required is False
    assert plan.stages == ()


def test_quality_mode_required_adds_minimum_review() -> None:
    plan = DomainQualityPlanner().plan(
        capability="general",
        quality_mode="required",
    )

    assert plan.required is True
    assert plan.stages == (QualityStage.THERMOS,)
