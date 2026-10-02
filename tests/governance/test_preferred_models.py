from openjarvis.core.config import HardwareInfo
from openjarvis.governance.model_selection import discover_local_candidates
from openjarvis.intelligence.model_catalog import BUILTIN_MODELS


def _spec(model_id: str):
    return next(spec for spec in BUILTIN_MODELS if spec.model_id == model_id)


def test_user_preference_prioritizes_compatible_local_model() -> None:
    hw = HardwareInfo(platform="windows", ram_gb=16.0)
    models = [
        _spec("qwen3.5:4b"),
        _spec("granite-code:3b"),
        _spec("ministral-3:3b"),
        _spec("llama3.2:3b"),
    ]

    candidates = discover_local_candidates(
        hw,
        "llamacpp",
        models,
        preferred_models=("granite-code:3b", "ministral-3:3b"),
    )

    assert candidates[0].spec.model_id == "granite-code:3b"


def test_gpt_oss_120b_is_not_viable_on_16gb_machine() -> None:
    hw = HardwareInfo(platform="windows", ram_gb=16.0)

    candidates = discover_local_candidates(
        hw,
        "llamacpp",
        [_spec("gpt-oss:120b"), _spec("llama3.2:3b")],
        preferred_models=("gpt-oss:120b", "llama3.2:3b"),
    )

    assert [candidate.spec.model_id for candidate in candidates] == ["llama3.2:3b"]


def test_preferred_catalog_entries_exist() -> None:
    ids = {spec.model_id for spec in BUILTIN_MODELS}

    assert "qwen3.5:4b" in ids
    assert "granite-code:3b" in ids
    assert "ministral-3:3b" in ids
    assert "gpt-oss:120b" in ids
    assert "llama3.2:3b" in ids
