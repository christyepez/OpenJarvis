from __future__ import annotations

from typing import Any, Iterable

DEFAULT_AUTONOMY_AGENT_NAME = "Jarvis Autonomous Operator V2"


def build_autonomy_runtime_config(
    *,
    model: str,
    workspace: str,
    runtime_device_id: str = "",
    runtime_machine: str = "trabajo",
    runtime_machine_candidates: Iterable[str] = ("trabajo", "MarketingIndo"),
    timezone: str = "America/Guayaquil",
) -> dict[str, Any]:
    """Build the governed managed-agent config used by every autonomy entrypoint."""
    instruction = (
        "Autonomous executor. Execute the latest user objective with REAL tools. "
        "You DO have execution tools. Only the tool schemas provided by the runtime "
        "for the current objective are available. Never invent or call a tool "
        "that is not "
        "explicitly listed for this objective. TOOL FIRST: for filesystem, "
        "process, test, Git, or system "
        "actions, call one of those tools before any prose. Never say that you cannot "
        "access the filesystem or execute commands when these tools are available. "
        "For write_file, path MUST be the exact absolute target FILE path from the "
        "objective; never pass the workspace directory itself as the path. "
        "Missing parent "
        "directories are recovered automatically by the runtime; do not create "
        "a directory "
        "using the target file path. "
        "Never claim execution without a successful tool result. The exact "
        "Windows workspace is "
        f"{workspace}. Use only real absolute paths in that workspace. "
        "For long work iterate change -> test -> verify -> commit/push when requested. "
        "Retry recoverable failures. Ask only for missing credentials, irreversible "
        "risk, or a decision that cannot be inferred. Output AUTONOMY_DONE only "
        "after every requested action has real evidence."
    )
    return {
        "model": model,
        "instruction": instruction,
        "system_prompt": instruction,
        "schedule_type": "interval",
        "schedule_value": 45,
        "timezone": timezone,
        "auto_pause_on_done": True,
        "completion_marker": "AUTONOMY_DONE",
        "completion_requires_tool_evidence": True,
        "compact_prompt": True,
        "temperature": 0.1,
        "max_turns": 12,
        "max_output_tokens": 256,
        "num_ctx": 4096,
        "timeout_seconds": 300,
        "max_stall_retries": 2,
        "workspace": workspace,
        "runtime_machine": runtime_machine,
        "runtime_machine_candidates": list(runtime_machine_candidates),
        "runtime_device_id": runtime_device_id,
        "runtime_machine_status": "online" if runtime_device_id else "unknown",
        "mcp_tools": True,
        "mcp_tool_allowlist": [
            "start_process",
            "read_process_output",
            "read_file",
            "write_file",
            "edit_block",
            "list_directory",
            "list_processes",
            "kill_process",
        ],
        "tools": [],
    }
