"""EasyTool-inspired compact discovery for OpenJarvis tool specifications."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

from openjarvis.tools._stubs import ToolSpec

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_STOP_WORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "for",
        "from",
        "in",
        "of",
        "on",
        "or",
        "the",
        "to",
        "use",
        "with",
        "this",
        "that",
        "my",
        "please",
    }
)


def _tokens(value: str) -> frozenset[str]:
    return frozenset(
        token
        for token in _TOKEN_RE.findall(value.casefold())
        if token not in _STOP_WORDS and len(token) > 1
    )


def _compact_text(value: str, max_chars: int = 140) -> str:
    compact = " ".join(value.split())
    if len(compact) <= max_chars:
        return compact
    return compact[: max_chars - 1].rstrip() + "…"


@dataclass(frozen=True, slots=True)
class CompactToolCard:
    """Small prompt-friendly representation of one relevant tool."""

    name: str
    category: str
    description: str
    required_params: tuple[str, ...]
    required_capabilities: tuple[str, ...]
    requires_confirmation: bool
    score: int

    def render(self) -> str:
        parts = [self.name]
        if self.category:
            parts[0] += f"[{self.category}]"
        parts.append(self.description)
        if self.required_params:
            parts.append("required=" + ",".join(self.required_params))
        if self.requires_confirmation:
            parts.append("confirm=yes")
        return " | ".join(parts)


def _required_params(spec: ToolSpec) -> tuple[str, ...]:
    required = spec.parameters.get("required", [])
    if not isinstance(required, list):
        return ()
    return tuple(sorted(str(value) for value in required if value))


def score_tool_relevance(
    query: str,
    *,
    name: str,
    description: str,
    category: str = "",
    parameter_names: Iterable[str] = (),
) -> int:
    """Score task/tool affinity without executing or instantiating a tool."""
    query_tokens = _tokens(query)
    return (
        8 * len(query_tokens & _tokens(name.replace("_", " ")))
        + 4 * len(query_tokens & _tokens(category))
        + 2 * len(query_tokens & _tokens(description))
        + len(query_tokens & _tokens(" ".join(parameter_names)))
    )


def _score(query: str, spec: ToolSpec) -> int:
    return score_tool_relevance(
        query,
        name=spec.name,
        description=spec.description,
        category=spec.category,
        parameter_names=(str(key) for key in spec.parameters.get("properties", {})),
    )


def discover_compact_tools(
    query: str,
    specs: Iterable[ToolSpec],
    *,
    limit: int = 6,
) -> list[CompactToolCard]:
    """Rank specs for *query* and return a bounded prompt-friendly catalog."""
    if limit <= 0:
        return []

    ranked: list[CompactToolCard] = []
    for spec in specs:
        ranked.append(
            CompactToolCard(
                name=spec.name,
                category=spec.category,
                description=_compact_text(spec.description),
                required_params=_required_params(spec),
                required_capabilities=tuple(sorted(spec.required_capabilities)),
                requires_confirmation=spec.requires_confirmation,
                score=_score(query, spec),
            )
        )

    ranked.sort(key=lambda card: (-card.score, card.name.casefold()))
    matches = [card for card in ranked if card.score > 0]
    if matches:
        return matches[:limit]
    return ranked[:limit]


def render_compact_tool_catalog(
    query: str,
    specs: Iterable[ToolSpec],
    *,
    limit: int = 6,
) -> str:
    """Render only the highest-value tool instructions for one task."""
    cards = discover_compact_tools(query, specs, limit=limit)
    return "\n".join(card.render() for card in cards)


__all__ = [
    "CompactToolCard",
    "discover_compact_tools",
    "render_compact_tool_catalog",
    "score_tool_relevance",
]
