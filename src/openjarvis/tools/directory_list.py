"""Native directory listing tool for authorized local workspaces."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from openjarvis.core.registry import ToolRegistry
from openjarvis.core.types import ToolResult
from openjarvis.tools._stubs import BaseTool, ToolSpec


@ToolRegistry.register("list_directory")
class ListDirectoryTool(BaseTool):
    """List one directory without recursion or file-content access."""

    tool_id = "list_directory"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="list_directory",
            description=(
                "List the immediate files and directories at an authorized path. "
                "Does not read file contents or recurse into child directories."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Absolute directory path to list.",
                    },
                    "max_entries": {
                        "type": "integer",
                        "description": "Maximum entries to return (default 200).",
                        "minimum": 1,
                        "maximum": 1000,
                    },
                    "include_hidden": {
                        "type": "boolean",
                        "description": (
                            "Include names beginning with a dot (default false)."
                        ),
                    },
                },
                "required": ["path"],
            },
            category="filesystem",
        )

    def execute(self, **params: Any) -> ToolResult:
        raw_path = str(params.get("path") or "").strip()
        if not raw_path:
            return ToolResult(
                tool_name=self.tool_id,
                content="No path provided.",
                success=False,
            )

        path = Path(raw_path).expanduser()
        if not path.exists():
            return ToolResult(
                tool_name=self.tool_id,
                content=f"Directory not found: {raw_path}",
                success=False,
            )
        if not path.is_dir():
            return ToolResult(
                tool_name=self.tool_id,
                content=f"Not a directory: {raw_path}",
                success=False,
            )

        try:
            max_entries = int(params.get("max_entries") or 200)
        except (TypeError, ValueError):
            max_entries = 200
        max_entries = max(1, min(max_entries, 1000))
        include_hidden = params.get("include_hidden") is True

        try:
            entries = sorted(
                path.iterdir(),
                key=lambda item: (not item.is_dir(), item.name.casefold()),
            )
        except OSError as exc:
            return ToolResult(
                tool_name=self.tool_id,
                content=f"Cannot list directory: {exc}",
                success=False,
            )

        visible = [
            item
            for item in entries
            if include_hidden or not item.name.startswith(".")
        ]
        selected = visible[:max_entries]
        lines = [
            f"[DIR] {item.name}" if item.is_dir() else f"[FILE] {item.name}"
            for item in selected
        ]
        if len(visible) > max_entries:
            lines.append(
                f"[TRUNCATED] {len(visible) - max_entries} additional entries"
            )

        content = "\n".join(lines) if lines else "[EMPTY]"
        return ToolResult(
            tool_name=self.tool_id,
            content=content,
            success=True,
            metadata={
                "path": str(path.resolve()),
                "count": len(selected),
                "total_visible": len(visible),
                "truncated": len(visible) > max_entries,
            },
        )


__all__ = ["ListDirectoryTool"]
