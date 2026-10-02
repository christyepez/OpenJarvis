from openjarvis.core.config import GpuInfo, HardwareInfo
from openjarvis.core.types import ModelSpec
from openjarvis.governance.model_selection import (
    discover_local_candidates,
    recommend_local_model,
)


def spec(model_id: str, params: float, *, min_vram: float = 0.0) -> ModelSpec:
    return ModelSpec(
        model_id=model_id,
        name=model_id,
        parameter_count_b=params,
        context_length=32768,
        min_vram_gb=min_vram,
        supported_engines=("ollama",),
        provider="test",
    )


def test_discovery_filters_models_that_do_not_fit() -> None:
    hw = HardwareInfo(
        platform="windows",
        ram_gb=32.0,
        gpu=GpuInfo(vendor="nvidia", name="test", vram_gb=8.0, count=1),
    )
    models = [spec("small", 4), spec("large", 30, min_vram=20)]

    candidates = discover_local_candidates(hw, "ollama", models)

    assert [candidate.spec.model_id for candidate in candidates] == ["small"]


def test_discovery_prefers_strongest_model_that_fits() -> None:
    hw = HardwareInfo(platform="windows", ram_gb=32.0)
    models = [spec("tiny", 2), spec("medium", 8), spec("large", 60)]

    candidates = discover_local_candidates(hw, "ollama", models)

    assert [candidate.spec.model_id for candidate in candidates] == ["medium", "tiny"]


def test_recommend_local_model_returns_best_fit() -> None:
    hw = HardwareInfo(platform="windows", ram_gb=16.0)
    models = [spec("tiny", 2), spec("medium", 8)]

    candidates = discover_local_candidates(hw, "ollama", models)
    assert candidates[0].spec.model_id == "medium"


def test_recommend_local_model_returns_catalog_model_or_none() -> None:
    hw = HardwareInfo(platform="windows", ram_gb=0.0)
    assert recommend_local_model(hw, "ollama") is None
