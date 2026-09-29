"""Managed local llama.cpp server discovery and startup."""

from __future__ import annotations

import glob
import os
import shutil
import socket
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import httpx


def find_llamacpp_executable(binary: str = "llama-server") -> str | None:
    """Locate llama.cpp binaries from PATH or common WinGet locations."""
    names = [binary, f"{binary}.exe"]
    for name in names:
        found = shutil.which(name)
        if found:
            return found

    if os.name == "nt":
        local_app_data = os.environ.get("LOCALAPPDATA", "")
        pattern = str(
            Path(local_app_data)
            / "Microsoft"
            / "WinGet"
            / "Packages"
            / "ggml.llamacpp*"
            / f"{binary}.exe"
        )
        matches = sorted(glob.glob(pattern))
        if matches:
            return matches[-1]
    return None


@dataclass(frozen=True, slots=True)
class LlamaCppServerConfig:
    """Arguments required to start one local llama-server."""

    model_path: str = ""
    hf_repo: str = ""
    hf_file: str = ""
    host: str = "127.0.0.1"
    port: int = 8080
    context_size: int = 8192
    threads: int = 0
    gpu_layers: int = 0
def build_server_command(
    config: LlamaCppServerConfig,
    *,
    executable: str | None = None,
) -> list[str]:
    """Build a deterministic llama-server command."""
    exe = executable or find_llamacpp_executable()
    if not exe:
        raise FileNotFoundError("llama-server executable was not found")

    command = [
        exe,
        "--host",
        config.host,
        "--port",
        str(config.port),
        "--ctx-size",
        str(config.context_size),
    ]
    if config.threads > 0:
        command.extend(["--threads", str(config.threads)])
    command.extend(["--gpu-layers", str(max(config.gpu_layers, 0))])

    if config.model_path:
        command.extend(["--model", config.model_path])
    elif config.hf_repo:
        command.extend(["--hf-repo", config.hf_repo])
        if config.hf_file:
            command.extend(["--hf-file", config.hf_file])
    else:
        raise ValueError("model_path or hf_repo is required")

    return command


def is_port_available(host: str, port: int) -> bool:
    """Return True when a TCP port can be bound locally."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
        except OSError:
            return False
    return True


def choose_port(
    host: str = "127.0.0.1",
    preferred: int = 8080,
    *,
    fallbacks: Sequence[int] = (18080, 28080, 38080),
) -> int:
    """Choose the first free local port without disturbing existing services."""
    for port in (preferred, *fallbacks):
        if is_port_available(host, port):
            return port
    raise OSError("No free llama.cpp port found in configured candidates")


def server_health(host: str = "127.0.0.1", port: int = 8080) -> bool:
    """Return True when a local llama-server responds."""
    try:
        response = httpx.get(f"http://{host}:{port}/health", timeout=1.5)
        return response.status_code < 500
    except Exception:
        return False


def start_server(
    config: LlamaCppServerConfig,
    *,
    executable: str | None = None,
    extra_args: Sequence[str] = (),
    stdout: int | None = subprocess.DEVNULL,
    stderr: int | None = subprocess.DEVNULL,
) -> subprocess.Popen[bytes]:
    """Start llama-server without a shell and return the process handle."""
    command = build_server_command(config, executable=executable)
    command.extend(extra_args)
    return subprocess.Popen(
        command,
        stdout=stdout,
        stderr=stderr,
        shell=False,
    )


__all__ = [
    "LlamaCppServerConfig",
    "build_server_command",
    "choose_port",
    "find_llamacpp_executable",
    "is_port_available",
    "server_health",
    "start_server",
]
