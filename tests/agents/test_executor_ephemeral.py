from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

REGISTRY_PATH = "openjarvis.core.registry.AgentRegistry.get"


def test_run_ephemeral_creates_and_runs_agent():
    from openjarvis.agents.executor import AgentExecutor

    manager = MagicMock()
    executor = AgentExecutor(manager=manager, event_bus=MagicMock())

    mock_agent_cls = MagicMock()
    mock_agent_instance = MagicMock()
    mock_agent_instance.run.return_value = MagicMock(content="Flushed.")
    mock_agent_cls.return_value = mock_agent_instance

    with patch(REGISTRY_PATH, return_value=mock_agent_cls):
        executor.run_ephemeral(
            agent_type="simple",
            system_prompt="Save important context.",
            input_text="Review and flush.",
        )
    assert mock_agent_instance.run.called


def test_run_ephemeral_passes_input():
    from openjarvis.agents.executor import AgentExecutor

    manager = MagicMock()
    executor = AgentExecutor(manager=manager, event_bus=MagicMock())

    mock_agent_cls = MagicMock()
    mock_agent_instance = MagicMock()
    mock_agent_instance.run.return_value = MagicMock(content="Done.")
    mock_agent_cls.return_value = mock_agent_instance

    with patch(REGISTRY_PATH, return_value=mock_agent_cls):
        executor.run_ephemeral(
            agent_type="simple",
            system_prompt="Test prompt.",
            input_text="Hello world",
        )
    mock_agent_instance.run.assert_called_once_with("Hello world")


def test_run_ephemeral_resolves_tools_and_preserves_security():
    from openjarvis.agents.executor import AgentExecutor
    from openjarvis.agents.simple import SimpleAgent
    from openjarvis.core.events import EventBus
    from openjarvis.core.registry import AgentRegistry, ToolRegistry
    from openjarvis.core.types import ToolResult
    from openjarvis.security.capabilities import CapabilityPolicy
    from openjarvis.tools._stubs import BaseTool, ToolSpec

    class _FlushProbe(BaseTool):
        calls = 0

        @property
        def spec(self):
            return ToolSpec(
                name="flush_probe",
                description="persist session state",
                required_capabilities=["memory:write"],
            )

        def execute(self, **params):
            type(self).calls += 1
            return ToolResult(tool_name="flush_probe", content="stored")

    class _RecordingLimiter:
        def __init__(self):
            self.keys = []

        def check(self, key):
            self.keys.append(key)
            return True, 0.0

    engine = MagicMock()
    engine.generate.side_effect = [
        {
            "content": "",
            "tool_calls": [{"id": "flush", "name": "flush_probe", "arguments": "{}"}],
            "finish_reason": "tool_calls",
        },
        {"content": "done", "finish_reason": "stop"},
    ]
    policy = CapabilityPolicy(default_deny=True)
    policy.grant("_default", "memory:write")
    policy.deny("ephemeral:simple", "memory:write")
    limiter = _RecordingLimiter()
    system = SimpleNamespace(
        engine=engine,
        model="test-model",
        capability_policy=policy,
        rate_limiter=limiter,
    )
    AgentRegistry.register_value("simple", SimpleAgent)
    ToolRegistry.register_value("flush_probe", _FlushProbe)
    executor = AgentExecutor(
        manager=MagicMock(),
        event_bus=EventBus(record_history=True),
        system=system,
    )

    result = executor.run_ephemeral(
        agent_type="simple",
        system_prompt="persist",
        input_text="flush now",
        tools=["flush_probe"],
    )

    assert len(result.tool_results) == 1
    assert "memory:write" in result.tool_results[0].content
    assert _FlushProbe.calls == 0
    assert limiter.keys == ["ephemeral:simple:flush_probe"]


def test_run_ephemeral_simple_agent_uses_local_worker_and_prompt_builder():
    from openjarvis.agents.executor import AgentExecutor
    from openjarvis.agents.simple import SimpleAgent
    from openjarvis.core.events import EventBus
    from openjarvis.core.registry import AgentRegistry

    engine = MagicMock()
    engine.engine_id = "ollama"
    engine.list_models.return_value = ["qwen3.5:4b", "granite-code:3b"]
    engine.generate.return_value = {
        "content": "done",
        "usage": {},
        "finish_reason": "stop",
    }
    system = SimpleNamespace(
        engine=engine,
        model="cloud-default",
        config=SimpleNamespace(
            governance=SimpleNamespace(
                prefer_local=True,
                preferred_models="qwen3.5:4b,granite-code:3b",
            )
        ),
    )
    AgentRegistry.register_value("simple", SimpleAgent)
    executor = AgentExecutor(
        manager=MagicMock(),
        event_bus=EventBus(record_history=True),
        system=system,
    )

    result = executor.run_ephemeral(
        agent_type="simple",
        system_prompt="You are a concise coding helper.",
        input_text="Refactor this Python function",
    )

    assert result.content == "done"
    assert engine.generate.call_args.kwargs["model"] == "granite-code:3b"
    messages = engine.generate.call_args.args[0]
    assert messages[0].role.value == "system"
    assert "concise coding helper" in messages[0].content
