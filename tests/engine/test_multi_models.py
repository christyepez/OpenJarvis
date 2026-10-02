from collections.abc import AsyncIterator, Sequence
from typing import Any

from openjarvis.core.events import EventBus
from openjarvis.core.types import Message
from openjarvis.engine._stubs import InferenceEngine
from openjarvis.engine.multi import MultiEngine
from openjarvis.telemetry.instrumented_engine import InstrumentedEngine


class _StubEngine(InferenceEngine):
    engine_id = "stub"

    def __init__(self, models: list[str]) -> None:
        self._models = models

    def generate(
        self,
        messages: Sequence[Message],
        *,
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        **kwargs: Any,
    ) -> dict[str, Any]:
        return {"content": "ok", "usage": {}}

    async def stream(
        self,
        messages: Sequence[Message],
        *,
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        yield "ok"

    def list_models(self) -> list[str]:
        return list(self._models)

    def health(self) -> bool:
        return True


def test_multi_engine_groups_models_by_engine() -> None:
    engine = MultiEngine(
        [
            ("ollama", _StubEngine(["qwen3.5:4b", "granite-code:3b"])),
            ("cloud", _StubEngine(["gpt-4o"])),
        ]
    )

    assert engine.models_by_engine() == {
        "ollama": ["qwen3.5:4b", "granite-code:3b"],
        "cloud": ["gpt-4o"],
    }


def test_instrumented_engine_preserves_grouped_model_discovery() -> None:
    multi = MultiEngine(
        [
            ("ollama", _StubEngine(["qwen3.5:4b"])),
            ("cloud", _StubEngine(["gpt-4o"])),
        ]
    )
    wrapped = InstrumentedEngine(multi, EventBus(record_history=False))

    assert wrapped.models_by_engine() == {
        "ollama": ["qwen3.5:4b"],
        "cloud": ["gpt-4o"],
    }
