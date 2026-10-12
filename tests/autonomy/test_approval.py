from __future__ import annotations

import pytest

from openjarvis.autonomy.approval import assess_approval


@pytest.mark.parametrize(
    ("goal", "reason"),
    [
        ("Despliega esta version a produccion", "production-change"),
        ("Elimina los archivos temporales", "destructive-change"),
        ("Envia un correo al cliente", "external-communication"),
        ("Realiza el pago de la factura", "financial-action"),
        ("Haz merge a main", "protected-branch-merge"),
        ("Cambia el password del servicio", "credential-change"),
    ],
)
def test_risk_based_policy_requires_approval_for_sensitive_goals(
    goal: str,
    reason: str,
) -> None:
    assessment = assess_approval(goal)

    assert assessment.required is True
    assert assessment.risk == "high"
    assert reason in assessment.reasons


def test_normal_development_goal_is_autonomous() -> None:
    assessment = assess_approval(
        "Revisa OpenJarvis corrige el codigo ejecuta las pruebas y haz commit"
    )

    assert assessment.required is False
    assert assessment.risk == "normal"
    assert assessment.reasons == ()


def test_always_policy_requires_approval() -> None:
    assessment = assess_approval("solo revisa el repo", policy="always")

    assert assessment.required is True
    assert assessment.reasons == ("policy-always",)


def test_never_policy_bypasses_risk_gate() -> None:
    assessment = assess_approval("despliega a produccion", policy="never")

    assert assessment.required is False
    assert assessment.risk == "accepted"


def test_invalid_policy_is_rejected() -> None:
    with pytest.raises(ValueError, match="invalid approval policy"):
        assess_approval("goal", policy="sometimes")
