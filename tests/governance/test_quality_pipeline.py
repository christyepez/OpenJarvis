from openjarvis.governance import (
    QualityPipelinePlanner,
    QualityStage,
)


def test_visual_code_change_orders_multimodal_before_quality_gates() -> None:
    plan = QualityPipelinePlanner().plan(
        has_code_changes=True,
        has_visual_changes=True,
        material_change=True,
    )

    assert plan.stages == (
        QualityStage.BUILD_TESTS,
        QualityStage.MULTIMODAL_REVIEW,
        QualityStage.ANTI_SLOP,
        QualityStage.THERMOS,
    )


def test_nonvisual_small_change_skips_multimodal_and_thermos() -> None:
    plan = QualityPipelinePlanner().plan(
        has_code_changes=True,
        has_visual_changes=False,
        material_change=False,
    )

    assert plan.stages == (
        QualityStage.BUILD_TESTS,
        QualityStage.ANTI_SLOP,
    )
def test_release_candidate_always_includes_thermos_and_release() -> None:
    plan = QualityPipelinePlanner().plan(
        has_code_changes=False,
        has_visual_changes=False,
        material_change=False,
        release_candidate=True,
    )

    assert plan.stages == (
        QualityStage.THERMOS,
        QualityStage.RELEASE,
    )
