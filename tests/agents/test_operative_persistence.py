from __future__ import annotations

import json

import pytest

from openjarvis.agents.operative import (
    OperativeAgent,
    _missing_parent_directory_call,
    _recover_text_tool_calls,
    _repair_write_file_arguments,
    _sanitize_tool_arguments,
    _uses_placeholder_path,
)
from openjarvis.sessions.session import SessionStore
from openjarvis.tools._stubs import BaseTool, ToolSpec
from openjarvis.core.types import ToolCall, ToolResult


class _ProbeTool(BaseTool):
    tool_id = "probe"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="probe",
            description="Safe autonomous execution probe.",
            parameters={"type": "object", "properties": {}},
        )

    def execute(self, **params) -> ToolResult:
        return ToolResult(tool_name="probe", content="probe-ok", success=True)


def test_repair_write_file_arguments_from_explicit_objective() -> None:
    objective = (
        r"NEW AUTONOMOUS OBJECTIVE. Use write_file for "
        r"C:\Users\chris\source\repos\OpenJarvis\docs\operations\smoke.md "
        "con el contenido Jarvis autonomous tool smoke passed. "
        "No hagas ninguna otra modificacion."
    )

    repaired = json.loads(_repair_write_file_arguments("{}", objective))

    assert repaired["path"].endswith(r"docs\operations\smoke.md")
    assert repaired["content"] == "Jarvis autonomous tool smoke passed"
    assert repaired["mode"] == "rewrite"


def test_repair_write_file_arguments_requires_explicit_content() -> None:
    objective = (
        r"Use write_file for "
        r"C:\Users\chris\source\repos\OpenJarvis\docs\operations\smoke.md"
    )

    assert _repair_write_file_arguments("{}", objective) == "{}"


def test_operative_session_round_trip(tmp_path) -> None:
    store = SessionStore(tmp_path / "sessions.db")
    try:
        agent = OperativeAgent(
            object(),
            "test-model",
            operator_id="jarvis-auto",
            session_store=store,
        )
        agent._save_session("objective one", "checkpoint one")

        messages = agent._load_session()

        assert [message.content for message in messages] == [
            "objective one",
            "checkpoint one",
        ]
    finally:
        store.close()


def test_recover_text_tool_call_only_for_allowed_tool() -> None:
    tools = [
        {
            "type": "function",
            "function": {"name": "read_file"},
        }
    ]
    calls = _recover_text_tool_calls(
        '{"name":"read_file","parameters":{"path":"C:/tmp/a.txt"}}',
        tools,
    )

    assert len(calls) == 1
    assert calls[0]["name"] == "read_file"
    assert '"path": "C:/tmp/a.txt"' in calls[0]["arguments"]


def test_recover_fenced_json_tool_call() -> None:
    tools = [
        {
            "type": "function",
            "function": {"name": "write_file"},
        }
    ]
    content = """## respuesta

```json
{"name":"write_file","parameters":{"path":"C:/tmp/a.txt","content":"ok","mode":"rewrite"}}
```

continua
"""
    calls = _recover_text_tool_calls(content, tools)

    assert len(calls) == 1
    assert calls[0]["name"] == "write_file"


def test_sanitize_tool_arguments_uses_schema() -> None:
    tools = [
        {
            "type": "function",
            "function": {
                "name": "read_file",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "offset": {"type": "number"},
                        "length": {"type": "number"},
                        "options": {"type": "object"},
                    },
                },
            },
        }
    ]
    raw = {
        "path": "C:/Users/chris/source/repos/OpenJarvis/docs/file.md",
        "offset": "0",
        "length": "100",
        "options": "{'mode': 'rewrite'}",
        "content": "{}",
        "mode": "rewrite",
    }

    sanitized = json.loads(_sanitize_tool_arguments("read_file", raw, tools))

    assert sanitized == {
        "path": "C:/Users/chris/source/repos/OpenJarvis/docs/file.md",
        "offset": 0.0,
        "length": 100.0,
        "options": {"mode": "rewrite"},
    }


def test_placeholder_path_guard_rejects_examples() -> None:
    assert _uses_placeholder_path('{"path":"/path/to/file"}') is True
    assert _uses_placeholder_path('{"path":"C:/Users/username/Documents/file.txt"}') is True
    assert _uses_placeholder_path('{"path":"/home/jarvis/project/file.txt"}') is True


def test_placeholder_path_guard_allows_real_workspace() -> None:
    assert (
        _uses_placeholder_path(
            '{"path":"C:/Users/chris/source/repos/OpenJarvis/docs/file.md"}'
        )
        is False
    )


def test_missing_parent_directory_recovery_uses_exact_parent() -> None:
    call = ToolCall(
        id="call-1",
        name="write_file",
        arguments=json.dumps(
            {
                "path": r"C:\Users\chris\source\repos\OpenJarvis\docs\operations\x.md",
                "content": "ok",
            }
        ),
    )
    result = ToolResult(
        tool_name="write_file",
        content="Error: ENOENT: no such file or directory",
        success=False,
    )
    tools = [
        {
            "type": "function",
            "function": {
                "name": "create_directory",
                "parameters": {"type": "object"},
            },
        }
    ]

    recovery = _missing_parent_directory_call(call, result, tools)

    assert recovery is not None
    assert recovery.name == "create_directory"
    assert json.loads(recovery.arguments)["path"] == (
        r"C:\Users\chris\source\repos\OpenJarvis\docs\operations"
    )


def test_recover_text_tool_call_rejects_unlisted_tool() -> None:
    tools = [
        {
            "type": "function",
            "function": {"name": "read_file"},
        }
    ]

    assert (
        _recover_text_tool_calls(
            '{"name":"shell_exec","parameters":{"command":"whoami"}}',
            tools,
        )
        == []
    )


def test_compact_prompt_skips_persona_expansion(monkeypatch) -> None:
    agent = OperativeAgent(object(), "test-model", compact_prompt=True)

    def fail_persona(prompt):
        pytest.fail("compact prompt must skip persona expansion")

    monkeypatch.setattr(agent, "_apply_persona", fail_persona)
    monkeypatch.setattr(
        agent,
        "_generate",
        lambda messages, **kwargs: {
            "content": "ok",
            "tool_calls": [],
            "usage": {},
            "finish_reason": "stop",
        },
    )

    result = agent.run("NEW AUTONOMOUS OBJECTIVE. inspect safely")

    assert result.content == "ok"


def test_new_autonomous_objective_retries_until_real_tool_call(monkeypatch) -> None:
    agent = OperativeAgent(
        object(),
        "test-model",
        tools=[_ProbeTool()],
        max_turns=4,
    )
    responses = iter(
        [
            {
                "content": "I already ran the tool. AUTONOMY_DONE",
                "tool_calls": [],
                "usage": {},
                "finish_reason": "stop",
            },
            {
                "content": "",
                "tool_calls": [
                    {
                        "id": "call-probe",
                        "name": "probe",
                        "arguments": "{}",
                    }
                ],
                "usage": {},
                "finish_reason": "tool_calls",
            },
            {
                "content": "Verified with real evidence. AUTONOMY_DONE",
                "tool_calls": [],
                "usage": {},
                "finish_reason": "stop",
            },
        ]
    )
    calls = 0

    def generate(messages, **kwargs):
        nonlocal calls
        calls += 1
        return next(responses)

    monkeypatch.setattr(agent, "_generate", generate)

    result = agent.run("NEW AUTONOMOUS OBJECTIVE. run the safe probe")

    assert calls == 3
    assert result.content == "Verified with real evidence. AUTONOMY_DONE"
    assert len(result.tool_results) == 1
    assert result.tool_results[0].tool_name == "probe"
    assert result.tool_results[0].success is True


def test_new_autonomous_objective_skips_stale_state_and_session(monkeypatch) -> None:
    agent = OperativeAgent(object(), "test-model")

    def fail_state():
        pytest.fail("stale state must not be loaded for a new objective")

    def fail_session():
        pytest.fail("stale session must not be loaded for a new objective")

    monkeypatch.setattr(agent, "_recall_state", fail_state)
    monkeypatch.setattr(agent, "_load_session", fail_session)
    monkeypatch.setattr(
        agent,
        "_generate",
        lambda messages, **kwargs: {
            "content": "checkpoint",
            "tool_calls": [],
            "usage": {},
            "finish_reason": "stop",
        },
    )

    wrapped_input = (
        "Current date: Wednesday, October 07, 2026\n\n"
        "Standing instruction: continue autonomously.\n\n"
        "New instructions:\n"
        "User: NEW AUTONOMOUS OBJECTIVE. validate runtime"
    )
    result = agent.run(wrapped_input)

    assert result.content == "checkpoint"
