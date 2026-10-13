from __future__ import annotations

from pathlib import Path


def test_n8n_deployment_is_version_pinned() -> None:
    root = Path(__file__).resolve().parents[2]
    compose = (root / "deploy" / "n8n" / "docker-compose.yml").read_text(
        encoding="utf-8"
    )
    env = (root / "deploy" / "n8n" / ".env.example").read_text(encoding="utf-8")

    assert "n8nio/n8n:2.42.6" in compose
    assert "N8N_IMAGE=n8nio/n8n:2.42.6" in env
    assert "n8nio/n8n:latest" not in compose
    assert "n8nio/n8n:latest" not in env


def test_n8n_workflow_environment_access_is_explicit() -> None:
    root = Path(__file__).resolve().parents[2]
    compose = (root / "deploy" / "n8n" / "docker-compose.yml").read_text(
        encoding="utf-8"
    )
    env = (root / "deploy" / "n8n" / ".env.example").read_text(encoding="utf-8")

    assert "N8N_BLOCK_ENV_ACCESS_IN_NODE" in compose
    assert "N8N_BLOCK_ENV_ACCESS_IN_NODE=false" in env


def test_n8n_scripts_have_local_node_fallback() -> None:
    root = Path(__file__).resolve().parents[2]
    start = (root / "deploy" / "n8n" / "start-n8n.ps1").read_text(encoding="utf-8")
    install = (root / "deploy" / "n8n" / "install-workflow.ps1").read_text(
        encoding="utf-8"
    )
    workflow_path = (
        root / "deploy" / "n8n" / "workflows" / "jarvis-task-dispatcher.json"
    )
    workflow = workflow_path.read_text(encoding="utf-8")

    assert "Start-N8nWithNode" in start
    assert "Ensure-NodeRuntime" in start
    assert "--legacy-peer-deps" in start
    assert "N8N_LISTEN_ADDRESS" in start
    assert "Install-WorkflowNode" in install
    assert '"id": "jarvis-task-dispatcher"' in workflow
