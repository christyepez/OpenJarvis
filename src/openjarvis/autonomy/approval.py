from __future__ import annotations

from dataclasses import asdict, dataclass
import re


@dataclass(frozen=True, slots=True)
class ApprovalAssessment:
    required: bool
    risk: str
    reasons: tuple[str, ...]

    def as_dict(self) -> dict:
        return asdict(self)


_HIGH_RISK_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\b(producci[oó]n|production|prod)\b", "production-change"),
    (r"\b(delete|remove|drop|truncate|elimina|borrar|borra)\b", "destructive-change"),
    (r"\b(send|email|correo|publica|publish|postea|mensaje externo)\b", "external-communication"),
    (r"\b(pay|payment|pago|transfer|transferencia|compra|purchase)\b", "financial-action"),
    (r"\b(merge|fusiona|fusionar)\b.*\b(main|master|release)\b", "protected-branch-merge"),
    (r"\b(secret|secreto|credential|credencial|token|password|contrase[nñ]a)\b", "credential-change"),
)


def assess_approval(goal: str, policy: str = "risk_based") -> ApprovalAssessment:
    normalized_policy = (policy or "risk_based").strip().lower()
    if normalized_policy not in {"risk_based", "always", "never"}:
        raise ValueError(f"invalid approval policy: {policy}")

    if normalized_policy == "always":
        return ApprovalAssessment(True, "high", ("policy-always",))
    if normalized_policy == "never":
        return ApprovalAssessment(False, "accepted", ())

    text = " ".join(str(goal or "").lower().split())
    reasons = tuple(
        reason
        for pattern, reason in _HIGH_RISK_PATTERNS
        if re.search(pattern, text, flags=re.IGNORECASE)
    )
    return ApprovalAssessment(
        required=bool(reasons),
        risk="high" if reasons else "normal",
        reasons=reasons,
    )
