from openjarvis.memory.context_router import ContextRouter, MemoryDomain


def test_context_router_detects_project_domain() -> None:
    route = ContextRouter().route(
        "Review the Docker build and deployment pipeline for this repository"
    )

    assert route.primary is MemoryDomain.PROJECT


def test_context_router_detects_personal_finance_without_forcing_project() -> None:
    route = ContextRouter().route(
        "Revisa mis movimientos del banco y el presupuesto de este mes"
    )

    assert route.primary is MemoryDomain.FINANCE
    assert MemoryDomain.PROJECT not in route.secondary
def test_context_router_supports_explicit_domain() -> None:
    route = ContextRouter().route(
        "status update",
        explicit_domain=MemoryDomain.COMMUNICATION,
    )

    assert route.primary is MemoryDomain.COMMUNICATION
    assert route.secondary == ()


def test_context_router_keeps_general_queries_general() -> None:
    route = ContextRouter().route("Tell me something interesting")

    assert route.primary is MemoryDomain.GENERAL
