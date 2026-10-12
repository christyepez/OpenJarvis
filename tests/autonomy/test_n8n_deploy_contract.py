from __future__ import annotations

from pathlib import Path


def test_n8n_deployment_is_version_pinned() -> None:
    root = Path(__file__).resolve().parents[2]
    compose = (root / "deploy" / "n8n" / "docker-compose.yml").read_text(
        encoding="utf-8"
    )
    env = (root / "deploy" / "n8n" / ".env.example").read_text(
        encoding="utf-8"
    )

    assert "n8nio/n8n:2.42.6" in compose
    assert "N8N_IMAGE=n8nio/n8n:2.42.6" in env
    assert "n8nio/n8n:latest" not in compose
    assert "n8nio/n8n:latest" not in env
