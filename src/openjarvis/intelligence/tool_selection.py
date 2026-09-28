"""EasyTool-inspired compact tool selection."""

from __future__ import annotations

import re
from typing import Any, Iterable

_TOKEN_RE = re.compile(r"[a-zA-Z0-9_]+")


def _tokens(text: str) -> set[str]:
    return {token.casefold() for token in _TOKEN_RE.findall(text) if len(token) > 2}


class CompactToolSelector:
    """Rank OpenAI-format tool specs against a query."""

    def select(
        self,
        query: str,
        specs: Iterable[dict[str, Any]],
        *,
        limit: int,
    ) -> list[dict[str, Any]]:
        candidates = list(specs)
        if limit <= 0 or len(candidates) <= limit:
            return candidates

        query_tokens = _tokens(query)
        ranked: list[tuple[int, int, str, dict[str, Any]]] = []
        for index, spec in enumerate(candidates):
            function = spec.get("function", {})
            name = str(function.get("name", ""))
            description = str(function.get("description", ""))
            haystack = f"{name} {description}"
            tool_tokens = _tokens(haystack)
            overlap = len(query_tokens & tool_tokens)
            exact = 1 if name and name.casefold() in query.casefold() else 0
            ranked.append((exact, overlap, name.casefold(), spec))

        ranked.sort(key=lambda item: (-item[0], -item[1], item[2]))

        selected = [item[3] for item in ranked[:limit]]
        # Keep deterministic original-schema objects; execution access is not
        # reduced, only the definitions advertised to the model.
        return selected


__all__ = ["CompactToolSelector"]
