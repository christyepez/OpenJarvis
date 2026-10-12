from __future__ import annotations

from pathlib import Path


def test_smoke_requires_verified_result_callback() -> None:
    root = Path(__file__).resolve().parents[2]
    script = (root / "deploy" / "n8n" / "smoke-autonomy.ps1").read_text(
        encoding="utf-8"
    )

    assert "resultCallbackDelivered" in script
    assert "AUTONOMY_V2_RESULT_CALLBACK=PASS" in script
    assert "AUTONOMY_V2_SMOKE=PASS" in script
    assert "[string]$SmokeModel = 'llama3.2:1b'" in script
    assert "model = $SmokeModel" in script
    assert "mcpToolAllowlist = @('list_directory')" in script
    assert "EXACT WINDOWS WORKSPACE" in script
    assert "lista el contenido del workspace usando list_directory" in script
