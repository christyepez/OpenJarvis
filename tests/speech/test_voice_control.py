from __future__ import annotations

from pathlib import Path

from openjarvis.speech.voice_control import (
    _autonomy_completion_requirements,
    _autonomy_tool_allowlist,
    _autonomy_tool_specs,
    _ground_autonomous_command,
    _is_autonomous_objective,
    _prepare_autonomy_models,
    _requires_tool_evidence,
    _summarize_list_directory_result,
    _wait_for_autonomy_idle,
    _wait_for_verified_autonomy_reply,
    audio_device_candidates,
    autonomous,
    direct,
    fallback_command,
    record_voice_audio,
    resolve_audio_device,
    wait_for_wake,
    wake_command,
)


def test_wake_command_accepts_spanish_whisper_jarvis_variant() -> None:
    woke, command = wake_command("Ya haréis prueba de voz.")
    assert woke is True
    assert command == "prueba de voz"


def test_wake_command_accepts_arbiz_variant() -> None:
    woke, command = wake_command("Y Arbiz verifica el directorio actual.")

    assert woke is True
    assert command == "verifica el directorio actual"


def test_wake_command_ignores_unrelated_speech() -> None:
    assert wake_command("esto es una conversación normal") == (False, "")


def test_fallback_command_ignores_unrelated_speech(monkeypatch) -> None:
    class Transcript:
        text = "esto es una conversación ambiental sin palabra de activación"

    class Backend:
        def transcribe(self, audio, format, language):
            return Transcript()

    monkeypatch.setattr(
        "openjarvis.speech.voice_control.record_voice_audio",
        lambda **kwargs: b"wav",
    )
    monkeypatch.setattr(
        "openjarvis.speech.voice_control.wav_rms",
        lambda audio: 500.0,
    )

    assert fallback_command(Backend()) == ""


def test_action_commands_require_real_tool_evidence() -> None:
    assert _requires_tool_evidence("verifica el directorio actual") is True
    assert _requires_tool_evidence("abre docker desktop") is True
    assert _requires_tool_evidence("lista el contenido del directorio") is True
    assert _requires_tool_evidence("cuanto es dos mas dos") is False


def test_autonomous_objective_requires_explicit_action() -> None:
    assert _is_autonomous_objective("implementa el ajuste completo del panel") is True
    assert _is_autonomous_objective("continua con la implementacion de Jarvis") is True
    assert _is_autonomous_objective("lista el contenido del directorio del proyecto") is True
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


def test_wait_for_autonomy_idle_waits_for_running_tick(monkeypatch) -> None:
    statuses = iter(["running", "idle"])
    ticks = iter([0.0, 0.1, 0.2])

    def fake_api(path, *args, **kwargs):
        if str(path).endswith("/runtime"):
            return {"worker_alive": True}
        return {"status": next(statuses)}

    monkeypatch.setattr(
        "openjarvis.speech.voice_control.api",
        fake_api,
    )
    monkeypatch.setattr(
        "openjarvis.speech.voice_control.time.monotonic",
        lambda: next(ticks),
    )
    monkeypatch.setattr(
        "openjarvis.speech.voice_control.time.sleep",
        lambda _seconds: None,
    )

    _wait_for_autonomy_idle("agent-1", timeout_seconds=1.0)


def test_wait_for_autonomy_idle_times_out_without_replacement(monkeypatch) -> None:
    ticks = iter([0.0, 0.1, 0.6])

    def fake_api(path, *args, **kwargs):
        if str(path).endswith("/runtime"):
            return {"worker_alive": True}
        return {"status": "running"}

    monkeypatch.setattr(
        "openjarvis.speech.voice_control.api",
        fake_api,
    )
    monkeypatch.setattr(
        "openjarvis.speech.voice_control.time.monotonic",
        lambda: next(ticks),
    )
    monkeypatch.setattr(
        "openjarvis.speech.voice_control.time.sleep",
        lambda _seconds: None,
    )

    import pytest

    with pytest.raises(TimeoutError):
        _wait_for_autonomy_idle("agent-1", timeout_seconds=0.5)


def test_wait_for_autonomy_idle_recovers_orphaned_running_tick(monkeypatch) -> None:
    calls: list[str] = []

    def fake_api(path, *args, **kwargs):
        calls.append(str(path))
        if str(path).endswith("/runtime"):
            return {"worker_alive": False}
        if str(path).endswith("/recover"):
            return {"recovered": True}
        return {"status": "running"}

    monkeypatch.setattr(
        "openjarvis.speech.voice_control.api",
        fake_api,
    )
    monkeypatch.setattr(
        "openjarvis.speech.voice_control.time.monotonic",
        lambda: 0.0,
    )

    _wait_for_autonomy_idle("agent-1", timeout_seconds=1.0)

    assert "/v1/managed-agents/agent-1/recover" in calls


def test_autonomy_tool_allowlist_keeps_directory_task_minimal() -> None:
    assert _autonomy_tool_allowlist(
        "Lista el contenido del workspace usando list_directory"
    ) == ["list_directory"]


def test_autonomy_tool_allowlist_keeps_e2e_task_focused() -> None:
    assert _autonomy_tool_allowlist(
        "Crea docs/test.md, ejecuta pytest, git diff, commit y push"
    ) == ["write_file", "start_process", "read_process_output"]


def test_autonomy_completion_requirements_include_process_exit_zero() -> None:
    requirements = _autonomy_completion_requirements(
        "ejecuta pytest, git status, git diff, commit y push; termina con exit code 0"
    )

    assert "pytest" in requirements
    assert "git_status" in requirements
    assert "git_diff" in requirements
    assert "git_commit" in requirements
    assert "git_push" in requirements
    assert "process_exit_0" in requirements


def test_autonomy_completion_requirements_include_process_gate() -> None:
    requirements = _autonomy_completion_requirements(
        "Usa start_process y termina solo si aparece [E2E] AUTONOMY_GATE_OK."
    )

    assert "process_start" in requirements
    assert "autonomy_gate_ok" in requirements


def test_autonomy_tool_specs_include_create_directory() -> None:
    specs = _autonomy_tool_specs(["create_directory"])
    create = specs[0]
    assert create["function"]["name"] == "create_directory"
    assert create["function"]["parameters"]["required"] == ["path"]


def test_autonomy_tool_specs_compact_start_process_schema() -> None:
    specs = _autonomy_tool_specs(["start_process", "read_process_output"])

    start = next(spec for spec in specs if spec["function"]["name"] == "start_process")
    params = start["function"]["parameters"]
    assert params["required"] == ["command", "timeout_ms"]
    assert set(params["properties"]) == {"command", "timeout_ms", "shell"}


def test_prepare_autonomy_models_unloads_competing_llms(monkeypatch) -> None:
    calls: list[tuple[list[str], dict]] = []

    monkeypatch.setattr(
        "openjarvis.speech.voice_control.subprocess.run",
        lambda args, **kwargs: calls.append((args, kwargs)),
    )
    monkeypatch.setattr(
        "openjarvis.speech.voice_control.MODEL",
        "qwen3.5:4b",
    )
    monkeypatch.setattr(
        "openjarvis.speech.voice_control.AUTONOMY_MODEL",
        "llama3.2:1b",
    )

    _prepare_autonomy_models()

    commands = [args for args, _ in calls]
    assert ["ollama", "stop", "jarvis-voice:latest"] in commands
    assert ["ollama", "stop", "granite-code:3b"] in commands
    assert ["ollama", "stop", "llama3.2:1b"] not in commands
    assert ["ollama", "stop", "qwen3.5:4b"] not in commands
    assert all(kwargs["encoding"] == "utf-8" for _, kwargs in calls)
    assert all(kwargs["errors"] == "replace" for _, kwargs in calls)


def test_resolve_audio_device_uses_system_default(monkeypatch) -> None:
    class FakeSoundDevice:
        default = type("Default", (), {"device": [7, 4]})()

    monkeypatch.setattr("openjarvis.speech.voice_control.AUDIO_DEVICE", "default")
    monkeypatch.setitem(__import__("sys").modules, "sounddevice", FakeSoundDevice())

    assert resolve_audio_device() == 7


def test_audio_device_candidates_falls_back_from_wasapi(monkeypatch) -> None:
    class FakeSoundDevice:
        default = type("Default", (), {"device": [0, 4]})()

        @staticmethod
        def query_hostapis():
            return [
                {"name": "MME", "default_input_device": 0},
                {"name": "Windows WASAPI", "default_input_device": 3},
            ]

        @staticmethod
        def query_devices():
            return [
                {"name": "Microphone Array", "max_input_channels": 2},
                {"name": "Speakers", "max_input_channels": 0},
                {"name": "AirPods", "max_input_channels": 1},
                {"name": "Headset Mic", "max_input_channels": 1},
            ]

    monkeypatch.setattr(
        "openjarvis.speech.voice_control.AUDIO_DEVICE",
        "wasapi-default",
    )
    monkeypatch.setitem(__import__("sys").modules, "sounddevice", FakeSoundDevice())

    assert audio_device_candidates() == [3, 0, 2]


def test_record_voice_audio_retries_next_device(monkeypatch) -> None:
    attempts: list[int | str | None] = []

    monkeypatch.setattr(
        "openjarvis.speech.voice_control.audio_device_candidates",
        lambda: [3, 0],
    )

    def fake_record_until_silence(*, device=None, **kwargs):
        attempts.append(device)
        if device == 3:
            raise RuntimeError("Unanticipated host error")
        return b"wav"

    monkeypatch.setattr(
        "openjarvis.speech.voice_control.record_until_silence",
        fake_record_until_silence,
    )

    assert record_voice_audio(max_seconds=1.0) == b"wav"
    assert attempts == [3, 0]


def test_wait_for_wake_retries_next_device(monkeypatch) -> None:
    attempts: list[int | str | None] = []

    monkeypatch.setattr(
        "openjarvis.speech.voice_control.audio_device_candidates",
        lambda: [3, 0],
    )

    def fake_wait(detector, device):
        attempts.append(device)
        if device == 3:
            raise RuntimeError("PortAudio host error")
        return 0.25

    monkeypatch.setattr(
        "openjarvis.speech.voice_control._wait_for_wake_on_device",
        fake_wait,
    )

    class Detector:
        def reset(self):
            return None

    assert wait_for_wake(Detector()) == 0.25
    assert attempts == [3, 0]



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


def test_direct_verifies_current_repository_directory(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        "openjarvis.speech.voice_control._repo_root",
        lambda: tmp_path,
    )

    class Result:
        returncode = 0
        stdout = str(tmp_path)

    calls: list[tuple[list[str], Path]] = []

    def fake_run(args, **kwargs):
        calls.append((args, kwargs["cwd"]))
        return Result()

    monkeypatch.setattr(
        "openjarvis.speech.voice_control.subprocess.run",
        fake_run,
    )

    answer = direct("verifica el directorio actual")

    assert answer == f"Directorio actual verificado: {tmp_path}."
    assert calls == [(["git", "rev-parse", "--show-toplevel"], tmp_path)]


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


def test_summarize_list_directory_result_counts_entries() -> None:
    listing = (
        "[DIR] src\n"
        "[FILE] README.md\n"
        "[DIR] tests\n"
        "[FILE] pyproject.toml\n"
    )

    assert _summarize_list_directory_result(listing) == (
        "Verifiqué el workspace. Encontré 2 carpetas y 2 archivos."
    )


def test_wait_for_verified_autonomy_reply_requires_success(monkeypatch) -> None:
    calls = 0

    def fake_api(path, payload=None, timeout=120, method=None):
        nonlocal calls
        if path.endswith("/messages"):
            calls += 1
            return {
                "messages": [
                    {
                        "direction": "agent_to_user",
                        "created_at": 20.0,
                        "content": "Directorio revisado correctamente.",
                        "tool_calls": [
                            {
                                "tool": "list_directory",
                                "result": "[DIR] src\n[FILE] README.md",
                                "success": True,
                            }
                        ],
                    }
                ]
            }
        return {"status": "idle"}

    monkeypatch.setattr("openjarvis.speech.voice_control.api", fake_api)

    content = _wait_for_verified_autonomy_reply(
        "agent-1",
        10.0,
        "list_directory",
        timeout_seconds=0.5,
    )

    assert content == "[DIR] src\n[FILE] README.md"
    assert calls == 1


def test_autonomous_returns_verified_list_directory_summary(monkeypatch) -> None:
    monkeypatch.setattr(
        "openjarvis.speech.voice_control._prepare_autonomy_models",
        lambda: None,
    )
    monkeypatch.setattr(
        "openjarvis.speech.voice_control._autonomy_config",
        lambda: {"instruction": "base"},
    )
    monkeypatch.setattr(
        "openjarvis.speech.voice_control._ground_autonomous_command",
        lambda command: command,
    )
    monkeypatch.setattr(
        "openjarvis.speech.voice_control._autonomy_tool_allowlist",
        lambda command: ["list_directory"],
    )
    monkeypatch.setattr(
        "openjarvis.speech.voice_control._autonomy_tool_specs",
        lambda names: [],
    )
    monkeypatch.setattr(
        "openjarvis.speech.voice_control._autonomy_completion_requirements",
        lambda command: [],
    )
    monkeypatch.setattr(
        "openjarvis.speech.voice_control._agent_id_by_name",
        lambda name: None,
    )
    monkeypatch.setattr(
        "openjarvis.speech.voice_control._autonomy_agent_id",
        lambda config: "agent-1",
    )
    monkeypatch.setattr(
        "openjarvis.speech.voice_control._wait_for_verified_autonomy_reply",
        lambda *args, **kwargs: "[DIR] src\n[FILE] README.md",
    )

    def fake_api(path, payload=None, timeout=120, method=None):
        if path == "/v1/operations/machines/probe":
            return {}
        if path.endswith("/messages") and payload is not None:
            return {"created_at": 10.0}
        if path.endswith("/run"):
            return {}
        if path.endswith("/agent-1"):
            return {"status": "idle"}
        return {}

    monkeypatch.setattr("openjarvis.speech.voice_control.api", fake_api)

    answer = autonomous("lista el contenido usando list_directory")

    assert answer == "Verifiqué el workspace. Encontré 1 carpetas y 1 archivos."


def test_autonomous_waits_before_reconciling_existing_agent(monkeypatch) -> None:
    order: list[str] = []

    monkeypatch.setattr(
        "openjarvis.speech.voice_control._prepare_autonomy_models",
        lambda: None,
    )
    monkeypatch.setattr(
        "openjarvis.speech.voice_control._autonomy_config",
        lambda: {"instruction": "base"},
    )
    monkeypatch.setattr(
        "openjarvis.speech.voice_control._ground_autonomous_command",
        lambda command: command,
    )
    monkeypatch.setattr(
        "openjarvis.speech.voice_control._autonomy_tool_allowlist",
        lambda command: [],
    )
    monkeypatch.setattr(
        "openjarvis.speech.voice_control._autonomy_tool_specs",
        lambda names: [],
    )
    monkeypatch.setattr(
        "openjarvis.speech.voice_control._autonomy_completion_requirements",
        lambda command: [],
    )
    monkeypatch.setattr(
        "openjarvis.speech.voice_control._agent_id_by_name",
        lambda name: "agent-1",
    )
    monkeypatch.setattr(
        "openjarvis.speech.voice_control._wait_for_autonomy_idle",
        lambda agent_id, timeout_seconds=45.0: order.append("wait"),
    )
    monkeypatch.setattr(
        "openjarvis.speech.voice_control._autonomy_agent_id",
        lambda config: order.append("reconcile") or "agent-1",
    )

    def fake_api(path, payload=None, timeout=120, method=None):
        if path.endswith("/agent-1"):
            return {"status": "idle"}
        return {}

    monkeypatch.setattr("openjarvis.speech.voice_control.api", fake_api)

    answer = autonomous("verifica el directorio actual")

    assert order == ["wait", "reconcile"]
    assert "Inicie el trabajo autonomo" in answer


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
    assert calls[0][1]["summary_memory"] == ""
    assert calls[0][1]["config"]["schedule_type"] == "interval"
    assert calls[0][1]["config"]["system_prompt"] == calls[0][1]["config"]["instruction"]
    assert calls[0][1]["config"]["model"] == "llama3.2:1b"
    assert calls[0][1]["config"]["max_output_tokens"] == 256
    assert "max_tokens" not in calls[0][1]["config"]
    assert calls[0][1]["config"]["num_ctx"] == 4096
    assert calls[0][1]["config"]["compact_prompt"] is True
    assert calls[0][1]["config"]["temperature"] == 0.1
    assert calls[0][1]["config"]["timeout_seconds"] == 300
    assert calls[0][1]["config"]["max_stall_retries"] == 2
    assert calls[0][1]["config"]["tools"] == []
    assert calls[0][1]["config"]["workspace"] in calls[0][1]["config"]["instruction"]
    assert "real absolute paths" in calls[0][1]["config"]["instruction"]
    assert "Only the tool schemas provided by the runtime" in calls[0][1]["config"]["instruction"]
