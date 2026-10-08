from __future__ import annotations

from pathlib import Path

from openjarvis.speech.voice_control import (
    _ground_autonomous_command,
    _is_autonomous_objective,
    _requires_tool_evidence,
    direct,
    resolve_audio_device,
    wake_command,
)


def test_wake_command_accepts_spanish_whisper_jarvis_variant() -> None:
    woke, command = wake_command("Ya haréis prueba de voz.")
    assert woke is True
    assert command == "prueba de voz"


def test_wake_command_ignores_unrelated_speech() -> None:
    assert wake_command("esto es una conversación normal") == (False, "")


def test_action_commands_require_real_tool_evidence() -> None:
    assert _requires_tool_evidence("verifica el directorio actual") is True
    assert _requires_tool_evidence("abre docker desktop") is True
    assert _requires_tool_evidence("cuanto es dos mas dos") is False


def test_autonomous_objective_requires_explicit_action() -> None:
    assert _is_autonomous_objective("implementa el ajuste completo del panel") is True
    assert _is_autonomous_objective("continua con la implementacion de Jarvis") is True
    assert _is_autonomous_objective("que va a hacer una cosa") is False
    assert _is_autonomous_objective("estado autonomo") is False


def test_ground_autonomous_command_expands_repo_paths() -> None:
    grounded = _ground_autonomous_command(
        "crea docs/jarvis-autonomy-e2e.md y ejecuta "
        "tests/agents/test_operative_persistence.py -q"
    )

    assert "EXACT WINDOWS WORKSPACE:" in grounded
    assert str(Path("docs") / "jarvis-autonomy-e2e.md") in grounded
    assert str(Path("tests") / "agents" / "test_operative_persistence.py") in grounded


def test_resolve_audio_device_uses_system_default(monkeypatch) -> None:
    class FakeSoundDevice:
        default = type("Default", (), {"device": [7, 4]})()

    monkeypatch.setattr("openjarvis.speech.voice_control.AUDIO_DEVICE", "default")
    monkeypatch.setitem(__import__("sys").modules, "sounddevice", FakeSoundDevice())

    assert resolve_audio_device() == 7


def test_direct_file_size_uses_real_local_file(
    tmp_path: Path,
    monkeypatch,
) -> None:
    target = tmp_path / "pyproject.toml"
    target.write_bytes(b"x" * 2048)
    monkeypatch.setenv("OPENJARVIS_VOICE_REPO", str(tmp_path))

    answer = direct("Jarvis dime el tamaño del archivo pyproject.toml")

    assert answer == "El archivo pyproject.toml tiene 2.0 kilobytes."


def test_direct_file_exists_uses_real_local_file(
    tmp_path: Path,
    monkeypatch,
) -> None:
    target = tmp_path / "pyproject.toml"
    target.write_text("ok", encoding="utf-8")
    monkeypatch.setenv("OPENJARVIS_VOICE_REPO", str(tmp_path))

    answer = direct("existe el archivo pyproject.toml")

    assert answer == "Si. El archivo pyproject.toml existe."


def test_direct_can_open_windows_explorer(monkeypatch) -> None:
    monkeypatch.setattr("openjarvis.speech.voice_control.os.name", "nt")
    launched: list[list[str]] = []

    class DummyProcess:
        pass

    def fake_popen(argv, **kwargs):
        launched.append(argv)
        return DummyProcess()

    monkeypatch.setattr("openjarvis.speech.voice_control.subprocess.Popen", fake_popen)

    answer = direct("abre el explorador")

    assert answer == "Abriendo el Explorador de archivos."
    assert launched == [["explorer.exe"]]


def test_direct_voice_help_lists_capabilities() -> None:
    answer = direct("que puedes hacer")

    assert answer is not None
    assert "Docker Desktop" in answer
    assert "estado del sistema" in answer


def test_direct_docker_status_uses_real_command_result(monkeypatch) -> None:
    class Result:
        returncode = 0
        stdout = "28.5.1\n"

    monkeypatch.setattr(
        "openjarvis.speech.voice_control.subprocess.run",
        lambda *args, **kwargs: Result(),
    )

    answer = direct("estado docker")

    assert answer == "Docker esta operativo. Version del servidor 28.5.1."


def test_execute_routes_conversation_directly_to_local_chat(monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr("openjarvis.speech.voice_control.direct", lambda command: None)
    monkeypatch.setattr(
        "openjarvis.speech.voice_control.chat",
        lambda command: calls.append("chat") or "respuesta local",
    )
    monkeypatch.setattr(
        "openjarvis.speech.voice_control.managed",
        lambda command: calls.append("managed") or "respuesta managed",
    )

    from openjarvis.speech.voice_control import execute

    assert execute("cuanto es dos mas dos") == "respuesta local"
    assert calls == ["chat"]


def test_execute_routes_actions_to_autonomous_agent(monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr("openjarvis.speech.voice_control.direct", lambda command: None)
    monkeypatch.setattr(
        "openjarvis.speech.voice_control.autonomous",
        lambda command: calls.append("autonomous") or "trabajo autonomo iniciado",
    )

    from openjarvis.speech.voice_control import execute

    assert execute("verifica el directorio actual") == "trabajo autonomo iniciado"
    assert calls == ["autonomous"]


def test_agent_lookup_ignores_archived_entries(monkeypatch) -> None:
    monkeypatch.setattr(
        "openjarvis.speech.voice_control.api",
        lambda *args, **kwargs: {
            "agents": [
                {
                    "id": "old",
                    "name": "Jarvis Autonomous Operator",
                    "status": "archived",
                },
                {"id": "new", "name": "Jarvis Autonomous Operator", "status": "idle"},
            ]
        },
    )

    from openjarvis.speech.voice_control import _agent_id_by_name

    assert _agent_id_by_name("Jarvis Autonomous Operator") == "new"


def test_existing_autonomy_agent_is_reconciled(monkeypatch) -> None:
    calls: list[tuple[str, dict | None, str | None]] = []

    monkeypatch.setattr(
        "openjarvis.speech.voice_control._agent_id_by_name",
        lambda name: "agent-1",
    )
    monkeypatch.setattr(
        "openjarvis.speech.voice_control._runtime_device_id",
        lambda: "device-1",
    )
    monkeypatch.setattr(
        "openjarvis.speech.voice_control.api",
        lambda path, payload=None, timeout=120, method=None: (
            calls.append((path, payload, method)) or {"id": "agent-1"}
        ),
    )

    from openjarvis.speech.voice_control import _autonomy_agent_id

    assert _autonomy_agent_id() == "agent-1"
    assert calls[0][0] == "/v1/managed-agents/agent-1"
    assert calls[0][2] == "PATCH"
    assert calls[0][1]["agent_type"] == "operative"
    assert calls[0][1]["config"]["schedule_type"] == "interval"
    assert calls[0][1]["config"]["model"] == "jarvis-voice:latest"
    assert calls[0][1]["config"]["timeout_seconds"] == 300
    assert calls[0][1]["config"]["max_stall_retries"] == 2
    assert calls[0][1]["config"]["workspace"] in calls[0][1]["config"]["instruction"]
    assert "C:/Users/username/Documents" in calls[0][1]["config"]["instruction"]
