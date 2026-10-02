from unittest.mock import patch

import pytest

from openjarvis.engine.llamacpp_runtime import (
    LlamaCppServerConfig,
    build_server_command,
    choose_port,
    find_llamacpp_executable,
    server_health,
)


def test_build_server_command_for_hf_model() -> None:
    config = LlamaCppServerConfig(
        hf_repo="tensorblock/Llama-3.2-3B-Instruct-GGUF",
        hf_file="Llama-3.2-3B-Instruct-Q4_K_M.gguf",
        port=8081,
        context_size=4096,
        threads=8,
    )

    command = build_server_command(config, executable="llama-server.exe")

    assert command[0] == "llama-server.exe"
    assert "--hf-repo" in command
    assert "tensorblock/Llama-3.2-3B-Instruct-GGUF" in command
    assert "--hf-file" in command
    assert "Llama-3.2-3B-Instruct-Q4_K_M.gguf" in command
    assert "--gpu-layers" in command


def test_build_server_command_requires_model() -> None:
    with pytest.raises(ValueError):
        build_server_command(
            LlamaCppServerConfig(),
            executable="llama-server.exe",
        )


def test_find_llamacpp_prefers_path() -> None:
    with patch("openjarvis.engine.llamacpp_runtime.shutil.which") as which:
        which.side_effect = lambda name: (
            "C:/tools/llama-server.exe" if "llama-server" in name else None
        )

        assert find_llamacpp_executable() == "C:/tools/llama-server.exe"


def test_choose_port_uses_fallback_when_preferred_is_busy() -> None:
    with patch(
        "openjarvis.engine.llamacpp_runtime.is_port_available",
        side_effect=lambda host, port: port == 18080,
    ):
        assert choose_port(preferred=8080) == 18080


def test_server_health_returns_false_on_connection_error() -> None:
    with patch(
        "openjarvis.engine.llamacpp_runtime.httpx.get",
        side_effect=RuntimeError("offline"),
    ):
        assert server_health() is False
