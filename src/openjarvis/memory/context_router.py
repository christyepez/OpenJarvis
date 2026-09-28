"""Multi-domain context routing for general-purpose personal memory."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class MemoryDomain(str, Enum):
    PERSONAL = "personal"
    PROFESSIONAL = "professional"
    PROJECT = "project"
    KNOWLEDGE = "knowledge"
    FINANCE = "finance"
    LEARNING = "learning"
    COMMUNICATION = "communication"
    TEMPORAL = "temporal"
    GENERAL = "general"


@dataclass(frozen=True, slots=True)
class ContextRoute:
    """Selected memory domains for one request."""

    primary: MemoryDomain
    secondary: tuple[MemoryDomain, ...] = ()
_DOMAIN_KEYWORDS: dict[MemoryDomain, tuple[str, ...]] = {
    MemoryDomain.PROJECT: (
        "repo", "repository", "project", "build", "deploy", "pipeline",
        "docker", "branch", "commit", "architecture", "sprint",
    ),
    MemoryDomain.FINANCE: (
        "bank", "budget", "invoice", "tax", "payment", "expense",
        "banco", "presupuesto", "factura", "impuesto", "pago", "gasto",
    ),
    MemoryDomain.COMMUNICATION: (
        "email", "mail", "meeting", "message", "reply", "calendar",
        "correo", "reunion", "mensaje", "responder", "calendario",
    ),
    MemoryDomain.LEARNING: (
        "learn", "course", "study", "training", "tutorial",
        "aprender", "curso", "estudiar", "capacitacion",
    ),
    MemoryDomain.PROFESSIONAL: (
        "career", "cv", "resume", "client", "job", "work",
        "carrera", "curriculum", "cliente", "empleo", "trabajo",
    ),
    MemoryDomain.PERSONAL: (
        "home", "family", "vehicle", "purchase", "routine",
        "casa", "familia", "vehiculo", "compra", "rutina",
    ),
    MemoryDomain.TEMPORAL: (
        "today", "tomorrow", "this week", "pending", "deadline",
        "hoy", "manana", "esta semana", "pendiente", "fecha limite",
    ),
    MemoryDomain.KNOWLEDGE: (
        "research", "paper", "document", "manual", "reference",
        "investigar", "articulo", "documento", "manual", "referencia",
    ),
}


class ContextRouter:
    """Route memory retrieval across domains without making projects dominant."""

    def route(
        self,
        query: str,
        *,
        explicit_domain: str | MemoryDomain | None = None,
    ) -> ContextRoute:
        if explicit_domain:
            return ContextRoute(primary=MemoryDomain(explicit_domain))

        normalized = query.casefold()
        scored: list[tuple[int, MemoryDomain]] = []
        for domain, keywords in _DOMAIN_KEYWORDS.items():
            score = sum(1 for keyword in keywords if keyword in normalized)
            if score:
                scored.append((score, domain))
        if not scored:
            return ContextRoute(primary=MemoryDomain.GENERAL)

        scored.sort(key=lambda item: (-item[0], item[1].value))
        primary = scored[0][1]
        secondary = tuple(domain for _, domain in scored[1:3])
        return ContextRoute(primary=primary, secondary=secondary)


__all__ = ["ContextRoute", "ContextRouter", "MemoryDomain"]
