from __future__ import annotations

from pathlib import Path


def _script() -> str:
    root = Path(__file__).resolve().parents[2]
    return (root / "deploy" / "n8n" / "bootstrap-autonomy-v2.ps1").read_text(
        encoding="utf-8"
    )


def test_bootstrap_runs_all_required_autonomy_steps() -> None:
    script = _script()

    assert "configure-openjarvis.ps1" in script
    assert "start-n8n.ps1" in script
    assert "install-workflow.ps1" in script
    assert "/v1/autonomy/status" in script
    assert "smoke-autonomy.ps1" in script
    assert "AUTONOMY_V2_BOOTSTRAP=PASS" in script


def test_bootstrap_configures_task_and_result_webhooks() -> None:
    script = _script()

    assert "/webhook/jarvis/task" in script
    assert "/webhook/jarvis/result" in script
    assert "-ResultWebhookUrl $ResultWebhookUrl" in script


def test_bootstrap_can_restart_openjarvis_scheduled_task() -> None:
    script = _script()

    assert "Get-ScheduledTask -TaskName 'OpenJarvis'" in script
    assert "Stop-ScheduledTask -TaskName 'OpenJarvis'" in script
    assert "Start-ScheduledTask -TaskName 'OpenJarvis'" in script
    assert "[switch]$SkipServiceRestart" in script
