from openjarvis.intelligence.tool_selection import CompactToolSelector


def tool(name: str, description: str) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {"type": "object", "properties": {}},
        },
    }


def test_compact_selector_prefers_relevant_tools() -> None:
    specs = [
        tool("calculator", "Perform arithmetic and math calculations"),
        tool("git_status", "Inspect repository git status"),
        tool("web_search", "Search the public web"),
        tool("file_read", "Read a local file"),
    ]

    selected = CompactToolSelector().select(
        "Check the repository git status",
        specs,
        limit=2,
    )

    names = [item["function"]["name"] for item in selected]
    assert "git_status" in names
def test_compact_selector_keeps_full_catalog_when_under_limit() -> None:
    specs = [tool("a_tool", "Alpha"), tool("b_tool", "Beta")]

    selected = CompactToolSelector().select("anything", specs, limit=5)

    assert selected == specs


def test_compact_selector_is_deterministic_for_zero_overlap() -> None:
    specs = [
        tool("zeta_tool", "Unrelated"),
        tool("alpha_tool", "Unrelated"),
    ]

    selected = CompactToolSelector().select("something else", specs, limit=1)

    assert selected[0]["function"]["name"] == "alpha_tool"
