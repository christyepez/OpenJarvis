from __future__ import annotations

from openjarvis.autonomy.planner import build_autonomy_plan


def test_code_goal_gets_engineering_quality_stages() -> None:
    plan = build_autonomy_plan(
        "Revisa el repositorio, corrige el codigo, ejecuta pruebas y haz commit"
    )

    ids = [step.id for step in plan.steps]
    assert plan.kind == "code"
    assert ids[:2] == ["inspect", "plan"]
    assert "implement" in ids
    assert "test" in ids
    assert "quality" in ids
    assert ids[-2:] == ["repair", "complete"]


def test_data_goal_gets_data_validation_stage() -> None:
    plan = build_autonomy_plan(
        "Ajusta el reporte Power BI y valida los datos de la matriz"
    )

    ids = [step.id for step in plan.steps]
    assert plan.kind == "data"
    assert "validate-data" in ids
    assert "apply" in ids


def test_deploy_goal_adds_deploy_and_smoke_stage() -> None:
    plan = build_autonomy_plan(
        "Actualiza el repo y luego despliega con Docker"
    )

    ids = [step.id for step in plan.steps]
    assert plan.kind == "code"
    assert "deploy" in ids


def test_general_goal_keeps_bounded_generic_execution() -> None:
    plan = build_autonomy_plan("Organiza esta tarea y completala")

    assert plan.kind == "general"
    ids = [step.id for step in plan.steps]
    assert ids == ["inspect", "plan", "execute", "repair", "complete"]


def test_plan_serializes_to_api_context_contract() -> None:
    payload = build_autonomy_plan("run tests in repo").as_dict()

    assert payload["kind"] == "code"
    assert payload["steps"][0]["id"] == "inspect"
    assert set(payload["steps"][0]) == {
        "id",
        "title",
        "objective",
        "verification",
    }
