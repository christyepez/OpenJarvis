from openjarvis.core.config import HardwareInfo
from openjarvis.governance.execution_router import (
    EngineModelRouter,
    match_catalog_model,
)
from openjarvis.intelligence.model_catalog import BUILTIN_MODELS


def _spec(model_id: str):
    return next(spec for spec in BUILTIN_MODELS if spec.model_id == model_id)


def test_runtime_alias_maps_to_llama_catalog_model() -> None:
    spec = match_catalog_model(
        "bartowski/Llama-3.2-1B-Instruct-GGUF",
        BUILTIN_MODELS,
    )

    assert spec is not None
    assert spec.model_id == "llama3.2:1b"


def test_cross_engine_router_prefers_local_over_codex() -> None:
    router = EngineModelRouter()
    route = router.route(
        models_by_engine={
            "llamacpp": ["bartowski/Llama-3.2-1B-Instruct-GGUF"],
            "cloud": ["codex/gpt-5-mini"],
        },
        catalog=BUILTIN_MODELS,
        hardware=HardwareInfo(platform="windows", ram_gb=16.0),
        preferred_models=(
            "codex/gpt-5-mini",
            "llama3.2:1b",
        ),
    )

    assert route is not None
    assert route.engine == "llamacpp"
    assert route.model == "llama3.2:1b"


def test_cross_engine_router_uses_codex_when_no_local_model_is_available() -> None:
    router = EngineModelRouter()
    route = router.route(
        models_by_engine={"cloud": ["codex/gpt-5-mini"]},
        catalog=BUILTIN_MODELS,
        hardware=HardwareInfo(platform="windows", ram_gb=16.0),
        preferred_models=("codex/gpt-5-mini",),
    )

    assert route is not None
    assert route.engine == "cloud"
    assert route.model == "codex/gpt-5-mini"


def test_unapproved_minimax_cloud_route_is_blocked() -> None:
    router = EngineModelRouter()
    route = router.route(
        models_by_engine={"cloud": ["MiniMax-M2.5"]},
        catalog=BUILTIN_MODELS,
        hardware=HardwareInfo(platform="windows", ram_gb=16.0),
    )

    assert route is None


def test_explicit_minimax_approval_allows_route() -> None:
    router = EngineModelRouter()
    route = router.route(
        models_by_engine={"cloud": ["MiniMax-M2.5"]},
        catalog=BUILTIN_MODELS,
        hardware=HardwareInfo(platform="windows", ram_gb=16.0),
        user_approved_paid=("minimax",),
    )

    assert route is not None
    assert route.model == "MiniMax-M2.5"


def test_oversized_gpt_oss_is_removed_from_local_candidates() -> None:
    router = EngineModelRouter()
    candidates = router.candidates(
        models_by_engine={
            "llamacpp": ["gpt-oss:120b", "llama3.2:3b"],
        },
        catalog=[_spec("gpt-oss:120b"), _spec("llama3.2:3b")],
        hardware=HardwareInfo(platform="windows", ram_gb=16.0),
        preferred_models=("gpt-oss:120b", "llama3.2:3b"),
    )

    assert [candidate.catalog_model_id for candidate in candidates] == [
        "llama3.2:3b"
    ]

def test_capability_routing_prefers_granite_for_coding() -> None:
    router = EngineModelRouter()
    route = router.route(
        models_by_engine={
            "ollama": ["qwen3.5:4b", "granite-code:3b"],
        },
        catalog=BUILTIN_MODELS,
        hardware=HardwareInfo(platform="windows", ram_gb=16.0),
        preferred_models=("qwen3.5:4b", "granite-code:3b"),
        capability="coding",
    )

    assert route is not None
    assert route.model == "granite-code:3b"
    assert "capability=coding" in route.reason


def test_capability_routing_prefers_qwen_for_multimodal() -> None:
    router = EngineModelRouter()
    route = router.route(
        models_by_engine={
            "ollama": ["granite-code:3b", "qwen3.5:4b"],
        },
        catalog=BUILTIN_MODELS,
        hardware=HardwareInfo(platform="windows", ram_gb=16.0),
        preferred_models=("granite-code:3b", "qwen3.5:4b"),
        capability="multimodal",
    )

    assert route is not None
    assert route.model == "qwen3.5:4b"
    assert "capability=multimodal" in route.reason
