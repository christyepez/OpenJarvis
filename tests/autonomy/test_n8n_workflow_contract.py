from __future__ import annotations

import json
from pathlib import Path


def _workflow() -> dict:
    root = Path(__file__).resolve().parents[2]
    path = root / "deploy" / "n8n" / "workflows" / "jarvis-task-dispatcher.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_n8n_workflow_contains_required_autonomy_nodes() -> None:
    workflow = _workflow()
    names = {node["name"] for node in workflow["nodes"]}

    assert {
        "Jarvis Task Webhook",
        "Normalize Jarvis Task",
        "Accept Task",
        "Callback OpenJarvis",
        "Start Managed Execution",
    }.issubset(names)


def test_n8n_workflow_starts_managed_execution_after_callback() -> None:
    workflow = _workflow()

    callback_targets = workflow["connections"]["Callback OpenJarvis"]["main"][0]
    assert callback_targets == [
        {
            "node": "Start Managed Execution",
            "type": "main",
            "index": 0,
        }
    ]

    execute_node = next(
        node
        for node in workflow["nodes"]
        if node["name"] == "Start Managed Execution"
    )
    url = execute_node["parameters"]["url"]
    assert "OPENJARVIS_BASE_URL" in url
    assert "/v1/autonomy/tasks/" in url
    assert "/execute" in url


def test_n8n_workflow_accepts_request_before_long_running_execution() -> None:
    workflow = _workflow()

    normalize_targets = workflow["connections"]["Normalize Jarvis Task"]["main"][0]
    assert normalize_targets[0]["node"] == "Accept Task"

    accept_targets = workflow["connections"]["Accept Task"]["main"][0]
    assert accept_targets[0]["node"] == "Callback OpenJarvis"
