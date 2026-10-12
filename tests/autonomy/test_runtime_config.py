from __future__ import annotations

from openjarvis.autonomy.runtime_config import build_autonomy_runtime_config


def test_runtime_config_keeps_governed_defaults() -> None:
    config = build_autonomy_runtime_config(
        model="qwen3.5:4b",
        workspace=r"C:\repo\OpenJarvis",
        runtime_device_id="device-1",
    )

    assert config["model"] == "qwen3.5:4b"
    assert config["workspace"] == r"C:\repo\OpenJarvis"
    assert config["runtime_machine"] == "trabajo"
    assert config["runtime_machine_candidates"] == ["trabajo", "MarketingIndo"]
    assert config["runtime_device_id"] == "device-1"
    assert config["runtime_machine_status"] == "online"
    assert config["completion_marker"] == "AUTONOMY_DONE"
    assert config["completion_requires_tool_evidence"] is True
    assert config["schedule_type"] == "interval"
    assert config["schedule_value"] == 45
    assert config["mcp_tools"] is True


def test_runtime_config_marks_missing_runtime_unknown() -> None:
    config = build_autonomy_runtime_config(
        model="qwen3.5:4b",
        workspace="C:/repo/OpenJarvis",
    )

    assert config["runtime_machine_status"] == "unknown"
    assert config["runtime_device_id"] == ""


def test_runtime_config_returns_fresh_mutable_lists() -> None:
    first = build_autonomy_runtime_config(model="m", workspace="w")
    second = build_autonomy_runtime_config(model="m", workspace="w")

    first["mcp_tool_allowlist"].append("extra")
    first["runtime_machine_candidates"].append("extra")

    assert "extra" not in second["mcp_tool_allowlist"]
    assert "extra" not in second["runtime_machine_candidates"]
