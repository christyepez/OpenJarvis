from openjarvis.core.registry import RouterPolicyRegistry
from openjarvis.intelligence.model_catalog import register_builtin_models
from openjarvis.learning.routing.local_first_policy import LocalFirstRouter
from openjarvis.learning.routing.router import build_routing_context


def test_local_first_prefers_local_model_over_cloud() -> None:
    register_builtin_models()
    router = LocalFirstRouter(
        available_models=["gpt-5-mini", "qwen3.5:2b"],
        default_model="gpt-5-mini",
    )

    selected = router.select_model(build_routing_context("Explain this design"))

    assert selected == "qwen3.5:2b"
def test_local_first_falls_back_to_cloud_when_no_local_model_exists() -> None:
    register_builtin_models()
    router = LocalFirstRouter(
        available_models=["gpt-5-mini", "gpt-5-mini-2025-08-07"],
        default_model="gpt-5-mini",
    )

    selected = router.select_model(build_routing_context("Explain this design"))

    assert selected in {"gpt-5-mini", "gpt-5-mini-2025-08-07"}


def test_local_first_policy_is_registered() -> None:
    import openjarvis.learning as learning

    learning.ensure_registered()
    assert RouterPolicyRegistry.get("local-first") is LocalFirstRouter
