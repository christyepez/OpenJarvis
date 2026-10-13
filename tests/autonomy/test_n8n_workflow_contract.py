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
        "Jarvis Result Webhook",
        "Acknowledge Jarvis Result",
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
        node for node in workflow["nodes"] if node["name"] == "Start Managed Execution"
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


def test_n8n_workflow_uses_explicit_normalized_task_references() -> None:
    workflow = _workflow()
    callback = next(
        node for node in workflow["nodes"] if node["name"] == "Callback OpenJarvis"
    )
    execute = next(
        node for node in workflow["nodes"] if node["name"] == "Start Managed Execution"
    )

    callback_url = callback["parameters"]["url"]
    callback_body = callback["parameters"]["body"]
    execute_url = execute["parameters"]["url"]
    task_ref = "$('Normalize Jarvis Task').item.json.taskId"

    assert "OPENJARVIS_BASE_URL" in callback_url
    assert "/v1/autonomy/callback" in callback_url
    assert task_ref in callback_body
    assert task_ref in execute_url


def test_n8n_workflow_exposes_result_webhook() -> None:
    workflow = _workflow()
    result_node = next(
        node for node in workflow["nodes"] if node["name"] == "Jarvis Result Webhook"
    )
    assert result_node["parameters"]["path"] == "jarvis/result"

    targets = workflow["connections"]["Jarvis Result Webhook"]["main"][0]
    assert targets == [
        {
            "node": "Acknowledge Jarvis Result",
            "type": "main",
            "index": 0,
        }
    ]


def test_n8n_workflow_exposes_health_webhook() -> None:
    workflow = _workflow()
    health_node = next(
        node for node in workflow["nodes"] if node["name"] == "Jarvis Health Webhook"
    )
    assert health_node["parameters"]["httpMethod"] == "GET"
    assert health_node["parameters"]["path"] == "jarvis/health"

    targets = workflow["connections"]["Jarvis Health Webhook"]["main"][0]
    assert targets == [
        {
            "node": "Acknowledge Jarvis Health",
            "type": "main",
            "index": 0,
        }
    ]
