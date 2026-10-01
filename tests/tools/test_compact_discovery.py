from openjarvis.tools._stubs import ToolSpec
from openjarvis.tools.compact_discovery import (
    discover_compact_tools,
    render_compact_tool_catalog,
)


def _spec(
    name: str,
    description: str,
    *,
    category: str = "",
    required: list[str] | None = None,
    confirm: bool = False,
) -> ToolSpec:
    required = required or []
    return ToolSpec(
        name=name,
        description=description,
        category=category,
        parameters={
            "type": "object",
            "properties": {key: {"type": "string"} for key in required},
            "required": required,
        },
        requires_confirmation=confirm,
    )


SPECS = [
    _spec(
        "git_status",
        "Inspect repository working tree and branch status.",
        category="git",
    ),
    _spec(
        "file_read",
        "Read source files from the local workspace.",
        category="filesystem",
        required=["path"],
    ),
    _spec(
        "web_search",
        "Search the public web for current information.",
        category="web",
        required=["query"],
    ),
    _spec(
        "shell_exec",
        "Execute an authorized local shell command.",
        category="system",
        required=["command"],
        confirm=True,
    ),
]


def test_discovery_prefers_repository_tools_for_code_query() -> None:
    cards = discover_compact_tools(
        "Inspect git repository status and read source files",
        SPECS,
        limit=3,
    )
    names = [card.name for card in cards]
    assert names[0] == "git_status"
    assert "file_read" in names
    assert "web_search" not in names


def test_discovery_exposes_required_params_and_confirmation() -> None:
    cards = discover_compact_tools(
        "run authorized command",
        SPECS,
        limit=1,
    )
    assert cards[0].name == "shell_exec"
    assert cards[0].required_params == ("command",)
    assert cards[0].requires_confirmation is True


def test_discovery_has_deterministic_fallback_and_limit() -> None:
    cards = discover_compact_tools("unrelated quantum request", SPECS, limit=2)
    assert [card.name for card in cards] == ["file_read", "git_status"]


def test_rendered_catalog_stays_compact() -> None:
    rendered = render_compact_tool_catalog(
        "search web and read file",
        SPECS,
        limit=2,
    )
    assert len(rendered.splitlines()) == 2
    assert "required=" in rendered
    assert len(rendered) < 420
