"""Machine selection for authorized local execution targets."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True, slots=True)
class MachineDescriptor:
    """Runtime facts used to select an execution machine."""

    name: str
    online: bool = True
    docker_available: bool = False
    gpu_available: bool = False
    tags: frozenset[str] = frozenset()


@dataclass(frozen=True, slots=True)
class MachineRequirement:
    """Task requirements used during machine selection."""

    require_docker: bool = False
    require_gpu: bool = False
    preferred_tags: frozenset[str] = frozenset()
class MachineRouter:
    """Prefer the configured primary machine, then deterministic fallbacks."""

    def __init__(
        self,
        *,
        primary: str = "trabajo",
        fallback_order: Iterable[str] = ("MarketingIndo",),
    ) -> None:
        self._primary = primary
        self._fallback_order = tuple(fallback_order)

    @property
    def primary(self) -> str:
        return self._primary

    def select(
        self,
        machines: Iterable[MachineDescriptor],
        requirement: MachineRequirement | None = None,
    ) -> MachineDescriptor | None:
        req = requirement or MachineRequirement()
        eligible = [m for m in machines if self._eligible(m, req)]
        if not eligible:
            return None

        preferred_names = (self._primary, *self._fallback_order)
        by_name = {m.name.lower(): m for m in eligible}
        for name in preferred_names:
            match = by_name.get(name.lower())
            if match is not None:
                return match

        return sorted(eligible, key=lambda item: item.name.lower())[0]
    @staticmethod
    def _eligible(machine: MachineDescriptor, req: MachineRequirement) -> bool:
        if not machine.online:
            return False
        if req.require_docker and not machine.docker_available:
            return False
        if req.require_gpu and not machine.gpu_available:
            return False
        if req.preferred_tags and not req.preferred_tags.issubset(machine.tags):
            return False
        return True


__all__ = [
    "MachineDescriptor",
    "MachineRequirement",
    "MachineRouter",
]
