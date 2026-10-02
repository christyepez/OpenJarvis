"""EasyTool-inspired compact tool selection."""

from __future__ import annotations

from typing import Any, Iterable

from openjarvis.tools.compact_discovery import score_tool_relevance


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

        ranked: list[tuple[int, str, dict[str, Any]]] = []
        for spec in candidates:
            function = spec.get("function", {})
            name = str(function.get("name", ""))
            description = str(function.get("description", ""))
            parameters = function.get("parameters", {}) or {}
            properties = parameters.get("properties", {})
            parameter_names = (
                [str(key) for key in properties] if isinstance(properties, dict) else []
            )
            score = score_tool_relevance(
                query,
                name=name,
                description=description,
                parameter_names=parameter_names,
            )
            if name and name.casefold() in query.casefold():
                score += 16
            ranked.append((score, name.casefold(), spec))

        ranked.sort(key=lambda item: (-item[0], item[1]))

        selected = [item[2] for item in ranked[:limit]]
        # Keep deterministic original-schema objects; execution access is not
        # reduced, only the definitions advertised to the model.
        return selected


__all__ = ["CompactToolSelector"]
