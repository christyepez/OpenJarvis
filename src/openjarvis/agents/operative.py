"""OperativeAgent — persistent, scheduled agent for autonomous operation.

Extends ToolUsingAgent with built-in session persistence and state recall.
Designed for Operators: autonomous agents that run on a schedule with
automatic state management between ticks.
"""

from __future__ import annotations

import ast
import json
import logging
import ntpath
import os
import re
from typing import Any, List, Optional

from openjarvis.agents._stubs import AgentContext, AgentResult, ToolUsingAgent
from openjarvis.core.events import EventBus
from openjarvis.core.registry import AgentRegistry
from openjarvis.core.types import Message, Role, ToolCall, ToolResult
from openjarvis.engine._stubs import InferenceEngine
from openjarvis.tools._stubs import BaseTool

logger = logging.getLogger(__name__)


def _recover_text_tool_calls(
    content: str,
    openai_tools: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Recover a single tool call serialized as plain text by small models."""
    raw = (content or "").strip()
    if not (raw.startswith("{") and raw.endswith("}")):
        fence_start = raw.find("```json")
        fence_end = raw.find("```", fence_start + 7) if fence_start >= 0 else -1
        if fence_start < 0 or fence_end < 0:
            return []
        if raw.find("```json", fence_start + 7) >= 0:
            return []
        raw = raw[fence_start + 7 : fence_end].strip()
        if not (raw.startswith("{") and raw.endswith("}")):
            return []

    parsed: Any
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        try:
            parsed = ast.literal_eval(raw)
        except (ValueError, SyntaxError):
            return []

    if not isinstance(parsed, dict):
        return []
    name = str(parsed.get("name") or "").strip()
    parameters = parsed.get("parameters")
    if not name or not isinstance(parameters, dict):
        return []

    allowed = {
        str((tool.get("function") or {}).get("name") or "").strip()
        for tool in openai_tools
        if isinstance(tool, dict)
    }
    if name not in allowed:
        return []

    return [
        {
            "id": "recovered_text_tool_call",
            "name": name,
            "arguments": json.dumps(parameters),
        }
    ]


def _coerce_tool_value(value: Any, schema: dict[str, Any]) -> Any:
    expected = schema.get("type")
    if expected in {"integer", "number"} and isinstance(value, str):
        try:
            return int(value) if expected == "integer" else float(value)
        except ValueError:
            return value
    if expected == "boolean" and isinstance(value, str):
        normalized = value.strip().casefold()
        if normalized in {"true", "1", "yes"}:
            return True
        if normalized in {"false", "0", "no"}:
            return False
        return value
    if expected in {"object", "array"} and isinstance(value, str):
        parsed: Any
        try:
            parsed = json.loads(value)
        except (json.JSONDecodeError, TypeError):
            try:
                parsed = ast.literal_eval(value)
            except (ValueError, SyntaxError):
                return value
        if expected == "object" and isinstance(parsed, dict):
            return parsed
        if expected == "array" and isinstance(parsed, list):
            return parsed
        return value
    if expected == "string" and not isinstance(value, str):
        return str(value)
    return value


def _sanitize_tool_arguments(
    name: str,
    arguments: Any,
    openai_tools: list[dict[str, Any]],
) -> str:
    """Drop unsupported fields and coerce simple types using the tool schema."""
    if isinstance(arguments, str):
        try:
            parsed = json.loads(arguments or "{}")
        except (json.JSONDecodeError, TypeError):
            return arguments
    elif isinstance(arguments, dict):
        parsed = arguments
    else:
        return json.dumps({})

    if not isinstance(parsed, dict):
        return json.dumps({})

    schema: dict[str, Any] = {}
    for tool in openai_tools:
        function = tool.get("function") if isinstance(tool, dict) else None
        if not isinstance(function, dict) or function.get("name") != name:
            continue
        parameters = function.get("parameters")
        if isinstance(parameters, dict):
            schema = parameters
        break

    properties = schema.get("properties")
    if not isinstance(properties, dict):
        return json.dumps(parsed)

    cleaned: dict[str, Any] = {}
    for key, value in parsed.items():
        field_schema = properties.get(key)
        if not isinstance(field_schema, dict):
            continue
        cleaned[key] = _coerce_tool_value(value, field_schema)

    return json.dumps(cleaned)


def _repair_write_file_arguments(arguments: str, objective: str) -> str:
    """Ground write_file path/content in explicit objective text when available."""
    try:
        parsed = json.loads(arguments or "{}")
    except (json.JSONDecodeError, TypeError):
        return arguments
    if not isinstance(parsed, dict):
        return arguments

    path_pattern = (
        r'([A-Za-z]:\\(?:[^\\/:*?"<>|\r\n]+\\)*'
        r'[^\\/:*?"<>|\r\n]+\.[A-Za-z0-9]{1,10})'
    )
    targeted_path = re.search(
        r"(?:write_file[^\r\n]{0,120}?|"
        r"(?:crea|crear|escribe|escribir)\s+(?:exactamente\s+)?)"
        + path_pattern,
        objective,
        flags=re.IGNORECASE,
    )
    path_matches = re.findall(
        path_pattern,
        objective,
        flags=re.IGNORECASE,
    )
    content_match = re.search(
        r"(?:con el contenido|with content)\s+(.+?)"
        r"(?=\.\s+(?:(?:\d+\)|No\b|Despues\b|Después\b|Then\b|"
        r"Do not\b|Solo\b|Only\b))|$)",
        objective,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not path_matches or not content_match:
        return arguments

    repaired = dict(parsed)
    repaired["path"] = (
        targeted_path.group(1).strip()
        if targeted_path is not None
        else path_matches[0].strip()
    )
    repaired["content"] = content_match.group(1).strip().rstrip(".")
    repaired["mode"] = "rewrite"
    return json.dumps(repaired)


def _missing_parent_directory_call(
    tool_call: ToolCall,
    tool_result: ToolResult,
    openai_tools: list[dict[str, Any]],
) -> ToolCall | None:
    """Return a create_directory recovery call for write_file ENOENT failures."""
    if tool_call.name != "write_file" or tool_result.success:
        return None
    if "enoent" not in str(tool_result.content or "").casefold():
        return None

    del openai_tools  # Availability is verified safely by ToolExecutor.

    try:
        args = json.loads(tool_call.arguments or "{}")
    except (json.JSONDecodeError, TypeError):
        return None
    path = str(args.get("path") or "").strip()
    if not path:
        return None
    parent = ntpath.dirname(path)
    if not parent or parent == path:
        return None

    return ToolCall(
        id=f"{tool_call.id}_mkdir",
        name="create_directory",
        arguments=json.dumps({"path": parent}),
    )



def _process_output_followup_call(
    tool_call: ToolCall,
    tool_result: ToolResult,
    openai_tools: list[dict[str, Any]],
) -> ToolCall | None:
    """Read output once for a process started by Commander in the same tool loop."""
    if tool_call.name != "start_process" or not tool_result.success:
        return None

    allowed = {
        str((tool.get("function") or {}).get("name") or "").strip()
        for tool in openai_tools
        if isinstance(tool, dict)
    }
    if "read_process_output" not in allowed:
        return None

    content = str(tool_result.content or "")
    if "process completed with exit code" in content.casefold():
        return None
    match = re.search(r"Process started with PID\s+(\d+)", content, re.IGNORECASE)
    if match is None:
        return None

    return ToolCall(
        id=f"{tool_call.id}_output",
        name="read_process_output",
        arguments=json.dumps(
            {
                "pid": int(match.group(1)),
                "offset": 0,
                "length": 200,
                "timeout_ms": 5000,
            }
        ),
    )


def _uses_placeholder_path(arguments: str) -> bool:
    """Reject obvious example paths before an autonomous tool can execute them."""
    try:
        parsed = json.loads(arguments or "{}")
    except (json.JSONDecodeError, TypeError):
        return False
    if not isinstance(parsed, dict):
        return False

    placeholders = (
        "/path/to/",
        "\\path\\to\\",
        "c:/users/username/",
        "c:\\users\\username\\",
        "/home/user/",
        "/home/jarvis/",
    )
    for key in ("path", "file_path", "working_directory", "cwd"):
        value = parsed.get(key)
        if isinstance(value, str):
            normalized = value.strip().casefold().replace("\\\\", "\\")
            if any(item in normalized for item in placeholders):
                return True
    return False


@AgentRegistry.register("operative")
class OperativeAgent(ToolUsingAgent):
    """Persistent autonomous agent with built-in state management.

    The Operative agent extends the standard tool-calling loop with:

    1. **Session loading** — restores conversation history from previous ticks.
    2. **State recall** — retrieves previous state JSON from memory backend.
    3. **System prompt** — injects the operator's protocol instructions.
    4. **Tool loop** — standard function-calling loop (same as Orchestrator).
    5. **Session save** — persists the tick's prompt and response.
    6. **State persistence** — auto-persists state if the agent didn't do it
       explicitly via memory_store tool.
    """

    agent_id = "operative"
    accepts_tools = True
    _default_temperature = 0.3
    _default_max_tokens = 2048
    _default_max_turns = 20

    def __init__(
        self,
        engine: InferenceEngine,
        model: str,
        *,
        tools: Optional[List[BaseTool]] = None,
        bus: Optional[EventBus] = None,
        max_turns: Optional[int] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        system_prompt: Optional[str] = None,
        operator_id: Optional[str] = None,
        session_store: Optional[Any] = None,
        memory_backend: Optional[Any] = None,
        interactive: bool = False,
        confirm_callback=None,
        prompt_builder: Optional[Any] = None,
        compact_prompt: bool = False,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            engine,
            model,
            tools=tools,
            bus=bus,
            max_turns=max_turns,
            temperature=temperature,
            max_tokens=max_tokens,
            interactive=interactive,
            confirm_callback=confirm_callback,
            prompt_builder=prompt_builder,
            **kwargs,
        )
        self._system_prompt = system_prompt or ""
        self._compact_prompt = compact_prompt
        self._operator_id = operator_id
        self._session_store = session_store
        self._memory_backend = memory_backend

    def run(
        self,
        input: str,
        context: Optional[AgentContext] = None,
        **kwargs: Any,
    ) -> AgentResult:
        """Execute a single operator tick."""
        self._emit_turn_start(input)

        # 1. Build system prompt with state context
        sys_parts: list[str] = []
        if self._system_prompt:
            sys_parts.append(self._system_prompt)

        new_objective = any(
            marker in input
            for marker in (
                "NEW AUTONOMOUS OBJECTIVE.",
                "CONTINUE AUTONOMOUS OBJECTIVE.",
            )
        )

        # 2. State recall from memory backend. A new autonomous objective must
        # not inherit stale state from a previous objective.
        previous_state = "" if new_objective else self._recall_state()
        if previous_state:
            sys_parts.append(f"\n## Previous State\n{previous_state}")

        system_prompt = "\n\n".join(sys_parts) if sys_parts else None
        # Compact autonomous mode intentionally skips persona/memory prompt
        # expansion so small local models see the tool-first objective clearly.
        if not self._compact_prompt:
            system_prompt = self._apply_persona(system_prompt)

        # 3. Load session history. New objectives start with a clean
        # conversational context while subsequent ticks keep continuity.
        session_messages = [] if new_objective else self._load_session()

        # 4. Build messages
        messages = self._build_operative_messages(
            input,
            context,
            system_prompt=system_prompt,
            session_messages=session_messages,
        )
        self._begin_tool_session_from_messages(messages)

        # 5. Run function-calling tool loop
        openai_tools = self._executor.get_openai_tools() if self._tools else []
        all_tool_results: list[ToolResult] = []
        turns = 0
        content = ""
        state_stored_by_tool = False
        missing_tool_retries = 0
        total_usage: dict[str, int] = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }

        for _turn in range(self._max_turns):
            turns += 1

            if self._loop_guard:
                messages = self._loop_guard.compress_context(messages)

            gen_kwargs: dict[str, Any] = {}
            if openai_tools:
                gen_kwargs["tools"] = openai_tools

            result = self._generate(messages, **gen_kwargs)
            usage = result.get("usage", {})
            for k in total_usage:
                total_usage[k] += usage.get(k, 0)
            content = result.get("content", "")
            raw_tool_calls = result.get("tool_calls", [])
            if not raw_tool_calls and openai_tools:
                raw_tool_calls = _recover_text_tool_calls(content, openai_tools)
                if raw_tool_calls:
                    logger.info(
                        "Recovered text-serialized tool call from model output"
                    )
                    content = ""

            if not raw_tool_calls:
                if (
                    openai_tools
                    and not all_tool_results
                    and missing_tool_retries < 2
                ):
                    missing_tool_retries += 1
                    messages.append(
                        Message(role=Role.ASSISTANT, content=content)
                    )
                    messages.append(
                        Message(
                            role=Role.USER,
                            content=(
                                "No real tool was executed. Do not narrate or claim "
                                "evidence. Call exactly one available tool required "
                                "for the objective now, using the real workspace and "
                                "valid arguments."
                            ),
                        )
                    )
                    continue
                content = self._check_continuation(result, messages)
                break

            tool_calls = []
            for i, tc in enumerate(raw_tool_calls):
                name = tc.get("name", "")
                arguments = _sanitize_tool_arguments(
                    name,
                    tc.get("arguments", "{}"),
                    openai_tools,
                )
                if name == "write_file":
                    arguments = _repair_write_file_arguments(arguments, input)
                tool_calls.append(
                    ToolCall(
                        id=tc.get("id", f"call_{i}"),
                        name=name,
                        arguments=arguments,
                    )
                )

            messages.append(
                Message(
                    role=Role.ASSISTANT,
                    content=content,
                    tool_calls=tool_calls,
                )
            )

            for tc in tool_calls:
                # Loop guard check
                if self._loop_guard:
                    verdict = self._loop_guard.check_call(tc.name, tc.arguments)
                    if verdict.blocked:
                        tool_result = ToolResult(
                            tool_name=tc.name,
                            content=f"Loop guard: {verdict.reason}",
                            success=False,
                        )
                        all_tool_results.append(tool_result)
                        messages.append(
                            Message(
                                role=Role.TOOL,
                                content=tool_result.content,
                                tool_call_id=tc.id,
                                name=tc.name,
                            )
                        )
                        continue

                if _uses_placeholder_path(tc.arguments):
                    tool_result = ToolResult(
                        tool_name=tc.name,
                        content=(
                            "Invalid placeholder path. Do not use example paths such as "
                            "/path/to/file, C:/Users/username, or /home/jarvis. "
                            "Retry using the exact Windows workspace and target path from "
                            "the standing instruction and current objective. If the objective "
                            "asks to create a known file, use write_file rather than read_file."
                        ),
                        success=False,
                        metadata={"arguments": tc.arguments},
                    )
                else:
                    tool_result = self._executor.execute(tc)
                    recovery_call = _missing_parent_directory_call(
                        tc,
                        tool_result,
                        openai_tools,
                    )
                    if recovery_call is not None:
                        try:
                            recovery_args = json.loads(recovery_call.arguments or "{}")
                            recovery_path = str(
                                recovery_args.get("path") or ""
                            ).strip()
                            os.makedirs(recovery_path, exist_ok=True)
                            recovery_result = ToolResult(
                                tool_name="create_directory",
                                content=(
                                    "Automatically created missing parent directory "
                                    f"{recovery_path}"
                                ),
                                success=True,
                                metadata={"arguments": recovery_call.arguments},
                            )
                        except (OSError, json.JSONDecodeError, TypeError) as exc:
                            recovery_result = ToolResult(
                                tool_name="create_directory",
                                content=f"Automatic parent directory recovery failed: {exc}",
                                success=False,
                                metadata={"arguments": recovery_call.arguments},
                            )
                        all_tool_results.append(recovery_result)
                        if recovery_result.success:
                            tool_result = self._executor.execute(tc)
                            if tool_result.success:
                                tool_result.content = (
                                    "Recovered missing parent directory and retried "
                                    f"write successfully. {tool_result.content}"
                                )

                    followup_call = _process_output_followup_call(
                        tc,
                        tool_result,
                        openai_tools,
                    )
                    if followup_call is not None:
                        followup_result = self._executor.execute(followup_call)
                        all_tool_results.append(followup_result)
                        if followup_result.content:
                            tool_result.content = (
                                f"{tool_result.content}\n\n"
                                "Process follow-up output:\n"
                                f"{followup_result.content}"
                            )
                all_tool_results.append(tool_result)

                # Track if agent stored state via memory_store
                if tc.name == "memory_store" and self._operator_id:
                    try:
                        args = json.loads(tc.arguments)
                        state_key = f"operator:{self._operator_id}:state"
                        if args.get("key", "") == state_key:
                            state_stored_by_tool = True
                    except (json.JSONDecodeError, TypeError):
                        pass

                messages.append(
                    Message(
                        role=Role.TOOL,
                        content=tool_result.content,
                        tool_call_id=tc.id,
                        name=tc.name,
                    )
                )
        else:
            # Max turns exceeded
            self._save_session(input, content)
            meta = dict(total_usage)
            meta["max_turns_exceeded"] = True
            return AgentResult(
                content=content or "Maximum turns reached without a final answer.",
                tool_results=all_tool_results,
                turns=turns,
                metadata=meta,
            )

        # 6. Save session
        self._save_session(input, content)

        # 7. Auto-persist state if agent didn't do it explicitly
        if not state_stored_by_tool:
            self._auto_persist_state(content)

        self._emit_turn_end(turns=turns, content_length=len(content))
        return AgentResult(
            content=content,
            tool_results=all_tool_results,
            turns=turns,
            metadata=total_usage,
        )

    def _build_operative_messages(
        self,
        input: str,
        context: Optional[AgentContext],
        *,
        system_prompt: Optional[str] = None,
        session_messages: Optional[list[Message]] = None,
    ) -> list[Message]:
        """Build message list with system prompt, session history, and input."""
        messages: list[Message] = []
        if system_prompt:
            messages.append(Message(role=Role.SYSTEM, content=system_prompt))
        # Inject session history (recent messages from previous ticks)
        if session_messages:
            messages.extend(session_messages)
        # Context conversation (e.g. memory injection)
        if context and context.conversation.messages:
            messages.extend(context.conversation.messages)
        messages.append(Message(role=Role.USER, content=input))
        return messages

    def _recall_state(self) -> str:
        """Retrieve previous operator state from memory backend."""
        if not self._memory_backend or not self._operator_id:
            return ""
        state_key = f"operator:{self._operator_id}:state"
        try:
            result = self._memory_backend.retrieve(state_key)
            if result:
                return result if isinstance(result, str) else str(result)
        except Exception:
            logger.debug("No previous state for operator %s", self._operator_id)
        return ""

    def _load_session(self) -> list[Message]:
        """Load recent session history for this operator."""
        if not self._session_store or not self._operator_id:
            return []
        session_id = f"operator:{self._operator_id}"
        try:
            session = self._session_store.get_or_create(session_id)
            if hasattr(session, "messages") and session.messages:
                # Return last 10 messages to avoid context overflow
                recent = session.messages[-10:]
                messages: list[Message] = []
                for item in recent:
                    if isinstance(item, dict):
                        role = item.get("role", "user")
                        content = item.get("content", "")
                    else:
                        role = getattr(item, "role", "user")
                        content = getattr(item, "content", "")
                    if not content:
                        continue
                    messages.append(
                        Message(
                            role=Role(str(role)),
                            content=str(content),
                        )
                    )
                return messages
        except Exception:
            logger.debug("Could not load session for operator %s", self._operator_id)
        return []

    def _save_session(self, input_text: str, response: str) -> None:
        """Save the tick's prompt and response to the session store."""
        if not self._session_store or not self._operator_id:
            return
        user_id = f"operator:{self._operator_id}"
        try:
            session = self._session_store.get_or_create(user_id)
            raw_session_id = getattr(session, "session_id", "")
            session_id = (
                raw_session_id
                if isinstance(raw_session_id, str) and raw_session_id
                else user_id
            )
            try:
                self._session_store.save_message(session_id, "user", input_text)
                self._session_store.save_message(session_id, "assistant", response)
            except TypeError:
                self._session_store.save_message(
                    session_id,
                    {"role": "user", "content": input_text},
                )
                self._session_store.save_message(
                    session_id,
                    {"role": "assistant", "content": response},
                )
        except Exception:
            logger.debug("Could not save session for operator %s", self._operator_id)

    def _auto_persist_state(self, content: str) -> None:
        """Auto-persist a state summary if the agent didn't store state explicitly."""
        if not self._memory_backend or not self._operator_id:
            return
        if not content or not content.strip():
            return
        state_key = f"operator:{self._operator_id}:state"
        try:
            # Store a summary of the agent's response as state
            summary = content[:1000]
            self._memory_backend.store(state_key, summary)
        except Exception:
            logger.debug(
                "Could not auto-persist state for operator %s",
                self._operator_id,
            )


__all__ = ["OperativeAgent"]
