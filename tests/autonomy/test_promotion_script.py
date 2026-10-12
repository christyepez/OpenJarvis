from __future__ import annotations

from pathlib import Path


def test_stable_promotion_requires_runtime_and_quality_gates() -> None:
    root = Path(__file__).resolve().parents[2]
    script = (root / "deploy" / "n8n" / "promote-autonomy-v2.ps1").read_text(
        encoding="utf-8"
    )

    assert "bootstrap-autonomy-v2.ps1" in script
    assert "tests/autonomy" in script
    assert "test_autonomy_routes.py" in script
    assert "ruff check" in script
    assert "docker compose" in script
    assert "git diff --check" in script
    assert 'AUTONOMY_V2_VERSION = "2.0.0"' in script
    assert "AUTONOMY_V2_STABLE=PASS" in script


def test_stable_promotion_requires_clean_tree_and_rc_source() -> None:
    root = Path(__file__).resolve().parents[2]
    script = (root / "deploy" / "n8n" / "promote-autonomy-v2.ps1").read_text(
        encoding="utf-8"
    )

    assert "git -C $RepoRoot status --porcelain" in script
    assert "2\.0\.0-rc" in script
    assert "Stable promotion requires a clean working tree." in script


def test_stable_promotion_commit_is_opt_in() -> None:
    root = Path(__file__).resolve().parents[2]
    script = (root / "deploy" / "n8n" / "promote-autonomy-v2.ps1").read_text(
        encoding="utf-8"
    )

    assert "[switch]$CreateCommit" in script
    assert "release: promote Autonomy V2 to 2.0.0" in script
