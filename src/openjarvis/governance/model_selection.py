"""Local-first model candidate discovery and ranking."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from openjarvis.core.config import HardwareInfo
from openjarvis.core.types import ModelSpec


@dataclass(frozen=True, slots=True)
class LocalModelCandidate:
    """A model that can plausibly run on the detected local hardware."""

    spec: ModelSpec
    engine: str
    estimated_memory_gb: float
    available_memory_gb: float

    @property
    def headroom_gb(self) -> float:
        return self.available_memory_gb - self.estimated_memory_gb


def available_model_memory_gb(hw: HardwareInfo) -> float:
    """Conservative memory budget for local inference."""
    if hw.gpu and hw.gpu.vram_gb > 0:
        return hw.gpu.vram_gb * max(hw.gpu.count, 1) * 0.9
    if hw.ram_gb > 0:
        return max((hw.ram_gb - 4.0) * 0.8, 0.0)
    return 0.0


def estimated_model_memory_gb(spec: ModelSpec) -> float:
    """Estimate Q4-class model memory when no stronger catalog hint exists."""
    min_vram = float(getattr(spec, "min_vram_gb", 0.0) or 0.0)
    active_b = float(getattr(spec, "active_parameter_count_b", 0.0) or 0.0)
    params_b = float(getattr(spec, "parameter_count_b", 0.0) or 0.0)
    estimated = max(active_b or params_b, 0.1) * 0.5 * 1.15
    return max(min_vram, estimated)


def discover_local_candidates(
    hw: HardwareInfo,
    engine: str,
    models: Iterable[ModelSpec] | None = None,
) -> list[LocalModelCandidate]:
    """Return compatible local candidates ordered from strongest fitting model."""
    if models is None:
        from openjarvis.intelligence.model_catalog import BUILTIN_MODELS

        models = BUILTIN_MODELS

    available = available_model_memory_gb(hw)
    if available <= 0:
        return []

    candidates: list[LocalModelCandidate] = []
    for spec in models:
        engines = tuple(getattr(spec, "supported_engines", ()) or ())
        if engine not in engines:
            continue
        estimated = estimated_model_memory_gb(spec)
        if estimated > available:
            continue
        candidates.append(
            LocalModelCandidate(
                spec=spec,
                engine=engine,
                estimated_memory_gb=estimated,
                available_memory_gb=available,
            )
        )
    # Prefer the largest model that fits.
    # Stable tie-breakers keep routing deterministic.
    candidates.sort(
        key=lambda item: (
            -float(
                getattr(item.spec, "active_parameter_count_b", 0.0)
                or getattr(item.spec, "parameter_count_b", 0.0)
                or 0.0
            ),
            -int(getattr(item.spec, "context_length", 0) or 0),
            str(getattr(item.spec, "model_id", "")),
        )
    )
    return candidates


def recommend_local_model(hw: HardwareInfo, engine: str) -> ModelSpec | None:
    """Choose the strongest catalogued model that fits local hardware."""
    candidates = discover_local_candidates(hw, engine)
    return candidates[0].spec if candidates else None


