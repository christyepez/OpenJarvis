"""Focused tests for canonical managed-agent tool resolution (#688)."""

from __future__ import annotations

from collections import Counter

import pytest

from openjarvis.agents import tool_resolver
from openjarvis.connectors.store import KnowledgeStore
from openjarvis.core.registry import ToolRegistry
from openjarvis.core.types import ToolResult
from openjarvis.tools import description_loader
from openjarvis.tools._stubs import BaseTool, ToolSpec
from openjarvis.tools.agent_tools import DomainTaskDispatchTool


class _AlphaTool(BaseTool):
    tool_id = "alpha"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(name="alpha", description="Alpha test tool")

    def execute(self, **params) -> ToolResult:
        return ToolResult(tool_name="alpha", content="alpha", success=True)


class _BetaTool(BaseTool):
    tool_id = "beta"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(name="beta", description="Beta test tool")

    def execute(self, **params) -> ToolResult:
        return ToolResult(tool_name="beta", content="beta", success=True)


class _NativeSharedTool(BaseTool):
    tool_id = "shared"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(name="shared", description="Native shared tool")

    def execute(self, **params) -> ToolResult:
        return ToolResult(tool_name="shared", content="native", success=True)


class _MCPSharedTool(BaseTool):
    tool_id = "shared"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(name="shared", description="MCP name collision")

    def execute(self, **params) -> ToolResult:
        return ToolResult(tool_name="shared", content="mcp", success=True)


class _MCPOnlyTool(BaseTool):
    tool_id = "mcp_only"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(name="mcp_only", description="MCP-only test tool")

    def execute(self, **params) -> ToolResult:
        return ToolResult(tool_name="mcp_only", content="mcp-only", success=True)


class _MCPDeviceTool(BaseTool):
    tool_id = "mcp_device"

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="start_process",
            description="Remote process tool",
            parameters={
                "type": "object",
                "properties": {
                    "deviceId": {"type": "string"},
                    "command": {"type": "string"},
                },
            },
        )

    def execute(self, **params) -> ToolResult:
        self.calls.append(dict(params))
        return ToolResult(
            tool_name="start_process",
            content=str(params.get("deviceId", "")),
            success=True,
        )


@pytest.fixture(autouse=True)
def _use_explicit_test_registrations(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep these unit tests independent of import-time registry population."""

    monkeypatch.setattr(tool_resolver, "ensure_registries_populated", lambda: None)


def test_deep_research_grants_are_live_deduplicated_and_use_selected_model(
    tmp_path,
) -> None:
    """Agent-type grants must beat duplicate bare configured tools."""

    db_path = tmp_path / "knowledge.db"
    with KnowledgeStore(db_path=db_path) as store:
        store.store(
            "The RESOLVER_SENTINEL decision was approved.",
            source="test",
            doc_type="note",
        )

    engine = object()
    resolved = tool_resolver.resolve_agent_tools(
        {
            "agent_type": "deep_research",
            "config": {
                # Both names are already supplied by the agent-type grant.
                "tools": ["knowledge_search", "think", "think"],
            },
        },
        engine=engine,
        model="agent-selected-model",
        knowledge_db_path=db_path,
    )

    try:
        names = [tool.spec.name for tool in resolved.instances]
        assert set(names) == {
            "knowledge_search",
            "knowledge_sql",
            "scan_chunks",
            "think",
        }
        assert all(count == 1 for count in Counter(names).values())

        search = resolved.by_name["knowledge_search"]
        result = search.execute(query="RESOLVER_SENTINEL")
        assert result.success is True
        assert "RESOLVER_SENTINEL" in result.content

        scan = resolved.by_name["scan_chunks"]
        assert scan._engine is engine
        assert scan._model == "agent-selected-model"
    finally:
        # All three knowledge tools share this store connection.
        resolved.by_name["knowledge_sql"]._store.close()


@pytest.mark.parametrize(
    "tool_config",
    [
        ["alpha", "beta", "alpha"],
        " alpha, beta, alpha ",
    ],
)
def test_configured_tools_normalize_lists_and_comma_separated_strings(
    tool_config,
) -> None:
    ToolRegistry.register_value("alpha", _AlphaTool)
    ToolRegistry.register_value("beta", _BetaTool)

    resolved = tool_resolver.resolve_agent_tools(
        {"agent_type": "simple", "config": {"tools": tool_config}},
        engine=object(),
        model="test-model",
    )

    assert [tool.spec.name for tool in resolved.instances] == ["alpha", "beta"]
    assert [spec["function"]["name"] for spec in resolved.openai_specs] == [
        "alpha",
        "beta",
    ]


def test_registered_tool_advertisement_matches_to_openai_function(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Runtime description overrides must reach canonical advertisements."""

    ToolRegistry.register_value("alpha", _AlphaTool)
    monkeypatch.setattr(
        description_loader,
        "get_tool_description_override",
        lambda name: "Runtime alpha description" if name == "alpha" else None,
    )

    resolved = tool_resolver.resolve_agent_tools(
        {"agent_type": "simple", "config": {"tools": ["alpha"]}},
        engine=object(),
        model="test-model",
    )

    tool = resolved.by_name["alpha"]
    assert resolved.openai_specs == [tool.to_openai_function()]
    assert (
        resolved.openai_specs[0]["function"]["description"]
        == "Runtime alpha description"
    )


def test_explicit_config_schema_takes_priority_over_tool_advertisement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ToolRegistry.register_value("alpha", _AlphaTool)
    monkeypatch.setattr(
        description_loader,
        "get_tool_description_override",
        lambda name: "Runtime alpha description" if name == "alpha" else None,
    )
    custom_spec = {
        "type": "function",
        "function": {
            "name": "alpha",
            "description": "Agent-specific alpha description",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        },
    }

    resolved = tool_resolver.resolve_agent_tools(
        {"agent_type": "simple", "config": {"tools": [custom_spec]}},
        engine=object(),
        model="test-model",
    )

    assert resolved.openai_specs == [custom_spec]
    assert resolved.by_name["alpha"].to_openai_function() == custom_spec


def test_invalid_tool_advertisement_falls_back_to_tool_spec() -> None:
    class _InvalidAdvertisementTool(_AlphaTool):
        def to_openai_function(self) -> dict[str, object]:
            raise RuntimeError("broken advertisement")

    ToolRegistry.register_value("alpha", _InvalidAdvertisementTool)

    resolved = tool_resolver.resolve_agent_tools(
        {"agent_type": "simple", "config": {"tools": ["alpha"]}},
        engine=object(),
        model="test-model",
    )

    assert resolved.openai_specs == [
        {
            "type": "function",
            "function": {
                "name": "alpha",
                "description": "Alpha test tool",
                "parameters": {},
            },
        }
    ]


def test_mcp_tools_merge_after_native_tools_without_name_collisions() -> None:
    ToolRegistry.register_value("shared", _NativeSharedTool)
    mcp_shared = _MCPSharedTool()
    mcp_only = _MCPOnlyTool()
    client = object()

    resolved = tool_resolver.resolve_agent_tools(
        {
            "agent_type": "simple",
            "config": {"tools": ["shared", "shared"]},
        },
        engine=object(),
        model="test-model",
        mcp_tools=[mcp_shared, mcp_only, mcp_only],
        mcp_clients=[client],
    )

    assert [tool.spec.name for tool in resolved.instances] == ["shared", "mcp_only"]
    assert isinstance(resolved.by_name["shared"], _NativeSharedTool)
    assert resolved.by_name["mcp_only"] is mcp_only
    assert resolved.mcp_clients == [client]
    assert [spec["function"]["name"] for spec in resolved.openai_specs] == [
        "shared",
        "mcp_only",
    ]


def test_mcp_tool_allowlist_filters_adapters() -> None:
    remote = _MCPDeviceTool()
    mcp_only = _MCPOnlyTool()

    resolved = tool_resolver.resolve_agent_tools(
        {
            "agent_type": "simple",
            "config": {
                "tools": [],
                "mcp_tool_allowlist": ["start_process"],
            },
        },
        engine=object(),
        model="test-model",
        mcp_tools=[remote, mcp_only],
    )

    assert list(resolved.by_name) == ["start_process"]
    assert "mcp_only" not in resolved.by_name


def test_mcp_device_tool_receives_runtime_device_default() -> None:
    remote = _MCPDeviceTool()

    resolved = tool_resolver.resolve_agent_tools(
        {
            "agent_type": "orchestrator",
            "config": {
                "tools": [],
                "runtime_machine": "MarketingIndo",
                "runtime_device_id": "device-marketing",
            },
        },
        engine=object(),
        model="test-model",
        mcp_tools=[remote],
    )

    result = resolved.by_name["start_process"].execute(command="echo ready")

    assert result.success is True
    assert result.content == "device-marketing"
    assert remote.calls == [
        {
            "deviceId": "device-marketing",
            "command": "echo ready",
        }
    ]

    override = resolved.by_name["start_process"].execute(
        command="echo override",
        deviceId="manual-device",
    )
    assert override.content == "manual-device"


def test_mcp_tools_can_be_disabled_per_agent() -> None:
    ToolRegistry.register_value("shared", _NativeSharedTool)

    class _MustNotIterate:
        def __iter__(self):
            raise AssertionError("MCP tools must not be inspected after opt-out")

    resolved = tool_resolver.resolve_agent_tools(
        {
            "agent_type": "simple",
            "config": {"tools": ["shared"], "mcp_tools": False},
        },
        engine=object(),
        model="test-model",
        mcp_tools=_MustNotIterate(),
        mcp_clients=_MustNotIterate(),
    )

    assert [tool.spec.name for tool in resolved.instances] == ["shared"]
    assert resolved.mcp_clients == []


def test_agent_workspace_binds_native_shell_and_git_defaults(tmp_path) -> None:
    class _WorkspaceShellTool(BaseTool):
        tool_id = "shell_exec"

        @property
        def spec(self) -> ToolSpec:
            return ToolSpec(name="shell_exec", description="workspace shell")

        def execute(self, **params) -> ToolResult:
            return ToolResult(
                tool_name="shell_exec",
                content=str(params.get("working_dir", "")),
                success=True,
            )

    class _WorkspaceGitTool(BaseTool):
        tool_id = "git_status"

        @property
        def spec(self) -> ToolSpec:
            return ToolSpec(name="git_status", description="workspace git")

        def execute(self, **params) -> ToolResult:
            return ToolResult(
                tool_name="git_status",
                content=str(params.get("repo_path", "")),
                success=True,
            )

    _WorkspaceShellTool.__module__ = "openjarvis.tools.shell_exec"
    _WorkspaceGitTool.__module__ = "openjarvis.tools.git_tool"
    ToolRegistry.register_value("shell_exec", _WorkspaceShellTool)
    ToolRegistry.register_value("git_status", _WorkspaceGitTool)

    workspace = str(tmp_path / "worktree")
    resolved = tool_resolver.resolve_agent_tools(
        {
            "agent_type": "orchestrator",
            "config": {
                "workspace": workspace,
                "tools": ["shell_exec", "git_status"],
            },
        },
        engine=object(),
        model="test-model",
    )

    assert resolved.by_name["shell_exec"].execute(command="pwd").content == workspace
    assert resolved.by_name["git_status"].execute().content == workspace
    assert (
        resolved.by_name["shell_exec"]
        .execute(
            command="pwd",
            working_dir="override",
        )
        .content
        == "override"
    )
    assert (
        resolved.by_name["git_status"].execute(repo_path="override").content
        == "override"
    )


def test_task_dispatch_receives_live_agent_manager_and_executor() -> None:
    ToolRegistry.register_value("task_dispatch", DomainTaskDispatchTool)
    manager = object()
    executor = object()

    resolved = tool_resolver.resolve_agent_tools(
        {
            "agent_type": "orchestrator",
            "config": {"tools": ["task_dispatch"]},
        },
        engine=object(),
        model="test-model",
        agent_manager=manager,
        agent_executor=executor,
    )

    tool = resolved.by_name["task_dispatch"]
    assert tool._manager is manager
    assert tool._executor is executor


def test_domain_worker_memory_tools_inherit_domain_default() -> None:
    from openjarvis.tools.storage_tools import MemoryStoreTool

    class _Backend:
        def __init__(self) -> None:
            self.metadata: list[dict[str, object]] = []

        def store(self, content, *, source="", metadata=None):
            self.metadata.append(dict(metadata or {}))
            return f"doc-{len(self.metadata)}"

    backend = _Backend()
    ToolRegistry.clear()
    ToolRegistry.register_value("memory_store", MemoryStoreTool)
    try:
        resolved = tool_resolver.resolve_agent_tools(
            {
                "agent_type": "orchestrator",
                "config": {
                    "domain": "finance",
                    "tools": ["memory_store"],
                },
            },
            engine=object(),
            model="test-model",
            memory_backend=backend,
        )

        first = resolved.by_name["memory_store"].execute(content="Budget decision")
        second = resolved.by_name["memory_store"].execute(
            content="Personal preference",
            domain="personal",
        )

        assert first.success is True
        assert second.success is True
        assert backend.metadata[0]["domain"] == "finance"
        assert backend.metadata[1]["domain"] == "personal"
    finally:
        ToolRegistry.clear()


def test_project_advance_receives_manager_and_executor():
    from openjarvis.agents.tool_resolver import instantiate_registered_tool
    from openjarvis.tools.agent_tools import ProjectAdvanceTool

    manager = object()
    executor = object()
    tool = instantiate_registered_tool(
        ProjectAdvanceTool,
        "project_advance",
        engine=None,
        model="",
        agent_manager=manager,
        agent_executor=executor,
    )

    assert tool._manager is manager
    assert tool._executor is executor
