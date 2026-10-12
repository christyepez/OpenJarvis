from __future__ import annotations

from pathlib import Path


def test_install_script_uses_n8n_2_publish_flow() -> None:
    root = Path(__file__).resolve().parents[2]
    script = (root / "deploy" / "n8n" / "install-workflow.ps1").read_text(
        encoding="utf-8"
    )

    assert "n8n import:workflow --input=$WorkflowPath" in script
    assert "n8n export:workflow --all" in script
    assert "n8n publish:workflow --id=$workflowId" in script
    assert "docker restart $Container" in script
    assert "update:workflow" not in script
