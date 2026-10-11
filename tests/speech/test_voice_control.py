from __future__ import annotations

import json
from pathlib import Path

from openjarvis.speech.voice_control import (
    AUTONOMY_MODEL,
    _autonomy_completion_requirements,
    _direct_explicit_file_delete,
    _direct_explicit_file_edit,
    _direct_explicit_file_write,
    _direct_explicit_git_branch,
    _direct_explicit_git_commit,
    _direct_explicit_git_push,
    _direct_explicit_main_sync,
    _direct_explicit_pr_create,
    _direct_explicit_pr_merge,
    _direct_explicit_pr_ready,
    _direct_explicit_pytest,
    _direct_prepare_branch_pr,
    _direct_finalize_current_pr,
    _autonomy_tool_allowlist,
    _autonomy_tool_specs,
    _ground_autonomous_command,
    _is_autonomous_objective,
    _ensure_api_available,
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


def test_capture_command_uses_short_followup_window(monkeypatch) -> None:
    recorded: dict[str, float] = {}

    class Transcript:
        text = "estado git"

    class Backend:
        def transcribe(self, audio, format, language):
            return Transcript()

    monkeypatch.setattr(
        "openjarvis.speech.voice_control.speak",
        lambda text: None,
    )

    def fake_record_voice_audio(**kwargs):
        recorded.update(kwargs)
        return b"wav"

    monkeypatch.setattr(
        "openjarvis.speech.voice_control.record_voice_audio",
        fake_record_voice_audio,
    )
    monkeypatch.setattr(
        "openjarvis.speech.voice_control.wav_rms",
        lambda audio: 500.0,
    )

    from openjarvis.speech.voice_control import capture_command

    assert capture_command(Backend()) == "estado git"
    assert recorded["startup_silence_seconds"] == 3.0
    assert recorded["max_seconds"] == 10.0


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


def test_ensure_api_available_restarts_unhealthy_backend(
    monkeypatch,
    tmp_path: Path,
) -> None:
    python = tmp_path / ".venv" / "Scripts" / "python.exe"
    python.parent.mkdir(parents=True)
    python.write_text("", encoding="utf-8")

    health = iter([False, True])
    runs: list[list[str]] = []
    launches: list[list[str]] = []

    monkeypatch.setattr(
        "openjarvis.speech.voice_control._api_healthy",
        lambda timeout=2.0: next(health),
    )
    monkeypatch.setattr(
        "openjarvis.speech.voice_control._repo_root",
        lambda: tmp_path,
    )
    monkeypatch.setattr(
        "openjarvis.speech.voice_control.subprocess.run",
        lambda args, **kwargs: runs.append(args),
    )
    monkeypatch.setattr(
        "openjarvis.speech.voice_control.subprocess.Popen",
        lambda args, **kwargs: launches.append(args),
    )

    assert _ensure_api_available(timeout_seconds=1.0) is True
    assert runs == [[str(python), "-m", "openjarvis.cli", "stop"]]
    assert launches[0][:4] == [str(python), "-m", "openjarvis.cli", "start"]


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



def test_direct_finalize_current_pr_runs_ready_then_merge(
    monkeypatch,
) -> None:
    calls: list[str] = []

    def fake_ready(command: str) -> str:
        calls.append("ready")
        return (
            "Pull request #55 listo para revision: "
            "https://github.com/example/repo/pull/55"
        )

    def fake_merge(command: str) -> str:
        calls.append("merge")
        return (
            "Pull request #55 fusionado con squash y verificado: "
            "https://github.com/example/repo/pull/55. "
            "Rama main activa y actualizada por fast-forward. HEAD abc1234."
        )

    monkeypatch.setattr(
        "openjarvis.speech.voice_control._direct_explicit_pr_ready",
        fake_ready,
    )
    monkeypatch.setattr(
        "openjarvis.speech.voice_control._direct_explicit_pr_merge",
        fake_merge,
    )

    answer = _direct_finalize_current_pr("finaliza el pr actual")

    assert calls == ["ready", "merge"]
    assert answer is not None
    assert answer.startswith("Pull request finalizado de forma segura.")
    assert "HEAD abc1234" in answer


def test_direct_finalize_current_pr_stops_before_merge(
    monkeypatch,
) -> None:
    merged = {"called": False}

    monkeypatch.setattr(
        "openjarvis.speech.voice_control._direct_explicit_pr_ready",
        lambda command: "No encuentro un pull request abierto para la rama actual.",
    )

    def fake_merge(command: str) -> str:
        merged["called"] = True
        return "unexpected"

    monkeypatch.setattr(
        "openjarvis.speech.voice_control._direct_explicit_pr_merge",
        fake_merge,
    )

    answer = _direct_finalize_current_pr(
        "finaliza el pull request actual"
    )

    assert answer == (
        "Detuve el flujo antes del merge. "
        "No encuentro un pull request abierto para la rama actual."
    )
    assert merged["called"] is False


def test_direct_prepare_branch_pr_orchestrates_safe_flow(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        "openjarvis.speech.voice_control._repo_root",
        lambda: tmp_path,
    )

    class Result:
        def __init__(self, stdout="", returncode=0):
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = ""

    responses = iter(
        [
            Result("feature/workflow\n"),
            Result(""),
            Result("feat: workflow orchestration\n"),
        ]
    )
    monkeypatch.setattr(
        "openjarvis.speech.voice_control.subprocess.run",
        lambda *args, **kwargs: next(responses),
    )
    monkeypatch.setattr(
        "openjarvis.speech.voice_control._direct_explicit_pytest",
        lambda command: "Pruebas completadas correctamente. 72 passed in 1.00s.",
    )
    monkeypatch.setattr(
        "openjarvis.speech.voice_control._direct_explicit_git_push",
        lambda command: (
            "Push completado y verificado para la rama feature/workflow en origin."
        ),
    )
    monkeypatch.setattr(
        "openjarvis.speech.voice_control._direct_explicit_pr_create",
        lambda command: (
            "Pull request draft creado y verificado: "
            "https://github.com/example/repo/pull/50"
        ),
    )

    answer = _direct_prepare_branch_pr(
        "prepara la rama actual para pull request"
    )

    assert answer is not None
    assert answer.startswith("Rama feature/workflow preparada para revision.")
    assert "72 passed" in answer
    assert "pull/50" in answer


def test_direct_prepare_branch_pr_stops_on_failed_tests(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        "openjarvis.speech.voice_control._repo_root",
        lambda: tmp_path,
    )

    class Result:
        def __init__(self, stdout="", returncode=0):
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = ""

    responses = iter([Result("feature/workflow\n"), Result("")])
    monkeypatch.setattr(
        "openjarvis.speech.voice_control.subprocess.run",
        lambda *args, **kwargs: next(responses),
    )
    monkeypatch.setattr(
        "openjarvis.speech.voice_control._direct_explicit_pytest",
        lambda command: "Las pruebas fallaron. 1 failed in 0.02s.",
    )

    pushed = {"value": False}
    monkeypatch.setattr(
        "openjarvis.speech.voice_control._direct_explicit_git_push",
        lambda command: pushed.__setitem__("value", True),
    )

    answer = _direct_prepare_branch_pr(
        "finaliza la rama actual para pr"
    )

    assert answer == (
        "Detuve el flujo porque las pruebas no pasaron. "
        "Las pruebas fallaron. 1 failed in 0.02s."
    )
    assert pushed["value"] is False


def test_direct_prepare_branch_pr_refuses_dirty_tracked_changes(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        "openjarvis.speech.voice_control._repo_root",
        lambda: tmp_path,
    )

    class Result:
        def __init__(self, stdout="", returncode=0):
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = ""

    responses = iter(
        [
            Result("feature/workflow\n"),
            Result(" M src/app.py\n"),
        ]
    )
    monkeypatch.setattr(
        "openjarvis.speech.voice_control.subprocess.run",
        lambda *args, **kwargs: next(responses),
    )

    answer = _direct_prepare_branch_pr(
        "prepara la rama actual para pr"
    )

    assert answer == (
        "Hay cambios versionados sin commit. No prepare el pull request; "
        "crea el commit primero."
    )


def test_direct_explicit_pr_ready_marks_draft_ready(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        "openjarvis.speech.voice_control._repo_root",
        lambda: tmp_path,
    )

    class Result:
        def __init__(self, returncode=0, stdout="", stderr=""):
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = stderr

    responses = iter(
        [
            Result(0, "feature/test\n"),
            Result(0, ""),
            Result(
                0,
                json.dumps(
                    {
                        "number": 42,
                        "url": "https://github.com/example/repo/pull/42",
                        "isDraft": True,
                        "state": "OPEN",
                        "baseRefName": "main",
                        "headRefName": "feature/test",
                    }
                ),
            ),
            Result(0, ""),
            Result(
                0,
                json.dumps(
                    {
                        "isDraft": False,
                        "url": "https://github.com/example/repo/pull/42",
                    }
                ),
            ),
        ]
    )
    monkeypatch.setattr(
        "openjarvis.speech.voice_control.subprocess.run",
        lambda *args, **kwargs: next(responses),
    )

    answer = _direct_explicit_pr_ready(
        "marca el pr actual listo para revision"
    )

    assert answer == (
        "Pull request #42 listo para revision: "
        "https://github.com/example/repo/pull/42"
    )


def test_direct_explicit_pr_merge_requires_clean_checks(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        "openjarvis.speech.voice_control._repo_root",
        lambda: tmp_path,
    )
    calls: list[list[str]] = []

    class Result:
        def __init__(self, returncode=0, stdout="", stderr=""):
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = stderr

    responses = iter(
        [
            Result(0, "feature/test\n"),
            Result(0, ""),
            Result(0, "deadbeefcafebabe\n"),
            Result(
                0,
                json.dumps(
                    {
                        "number": 42,
                        "url": "https://github.com/example/repo/pull/42",
                        "isDraft": False,
                        "state": "OPEN",
                        "baseRefName": "main",
                        "headRefName": "feature/test",
                        "mergeStateStatus": "CLEAN",
                        "statusCheckRollup": [
                            {
                                "name": "tests",
                                "status": "COMPLETED",
                                "conclusion": "SUCCESS",
                            }
                        ],
                    }
                ),
            ),
            Result(0, ""),
            Result(
                0,
                json.dumps(
                    {
                        "state": "MERGED",
                        "mergedAt": "2026-10-11T00:00:00Z",
                        "url": "https://github.com/example/repo/pull/42",
                    }
                ),
            ),
        ]
    )

    def fake_run(args, **kwargs):
        calls.append(args)
        return next(responses)

    monkeypatch.setattr(
        "openjarvis.speech.voice_control.subprocess.run",
        fake_run,
    )
    monkeypatch.setattr(
        "openjarvis.speech.voice_control._direct_explicit_main_sync",
        lambda command: "Rama main activa y actualizada por fast-forward. HEAD cafefeed.",
    )

    answer = _direct_explicit_pr_merge(
        "fusiona el pr actual con squash"
    )

    assert answer == (
        "Pull request #42 fusionado con squash y verificado: "
        "https://github.com/example/repo/pull/42. "
        "Rama main activa y actualizada por fast-forward. HEAD cafefeed."
    )
    assert calls[-2] == [
        "gh",
        "pr",
        "merge",
        "42",
        "--squash",
        "--match-head-commit",
        "deadbeefcafebabe",
    ]


def test_direct_explicit_pr_merge_refuses_pending_checks(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        "openjarvis.speech.voice_control._repo_root",
        lambda: tmp_path,
    )

    class Result:
        def __init__(self, stdout="", returncode=0):
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = ""

    responses = iter(
        [
            Result("feature/test\n"),
            Result(""),
            Result("deadbeef\n"),
            Result(
                json.dumps(
                    {
                        "number": 42,
                        "url": "https://github.com/example/repo/pull/42",
                        "isDraft": False,
                        "state": "OPEN",
                        "baseRefName": "main",
                        "headRefName": "feature/test",
                        "mergeStateStatus": "CLEAN",
                        "statusCheckRollup": [
                            {
                                "name": "tests",
                                "status": "IN_PROGRESS",
                                "conclusion": "",
                            }
                        ],
                    }
                )
            ),
        ]
    )
    monkeypatch.setattr(
        "openjarvis.speech.voice_control.subprocess.run",
        lambda *args, **kwargs: next(responses),
    )

    answer = _direct_explicit_pr_merge(
        "fusiona el pull request actual con squash"
    )

    assert answer == "El pull request tiene checks pendientes: tests."


def test_direct_explicit_pr_merge_refuses_draft(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        "openjarvis.speech.voice_control._repo_root",
        lambda: tmp_path,
    )

    class Result:
        def __init__(self, stdout="", returncode=0):
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = ""

    responses = iter(
        [
            Result("feature/test\n"),
            Result(""),
            Result("deadbeef\n"),
            Result(
                json.dumps(
                    {
                        "number": 42,
                        "url": "https://github.com/example/repo/pull/42",
                        "isDraft": True,
                        "state": "OPEN",
                        "baseRefName": "main",
                        "headRefName": "feature/test",
                        "mergeStateStatus": "CLEAN",
                        "statusCheckRollup": [],
                    }
                )
            ),
        ]
    )
    monkeypatch.setattr(
        "openjarvis.speech.voice_control.subprocess.run",
        lambda *args, **kwargs: next(responses),
    )

    answer = _direct_explicit_pr_merge(
        "fusiona el pr actual con squash"
    )

    assert answer == (
        "El pull request sigue en draft. Marcalo listo para revision primero."
    )


def test_direct_explicit_pr_create_creates_draft_for_synced_branch(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        "openjarvis.speech.voice_control._repo_root",
        lambda: tmp_path,
    )
    calls: list[list[str]] = []

    class Result:
        def __init__(self, returncode=0, stdout="", stderr=""):
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = stderr

    responses = iter(
        [
            Result(0, "feature/test\n"),
            Result(0, ""),
            Result(0, "origin/feature/test\n"),
            Result(0, ""),
            Result(0, "0\t0\n"),
            Result(0, ""),
            Result(0, "[]\n"),
            Result(0, "https://github.com/example/repo/pull/42\n"),
        ]
    )

    def fake_run(args, **kwargs):
        calls.append(args)
        return next(responses)

    monkeypatch.setattr(
        "openjarvis.speech.voice_control.subprocess.run",
        fake_run,
    )

    answer = _direct_explicit_pr_create(
        "crea un pull request con titulo Mejora segura "
        "y descripcion Validacion determinista"
    )

    assert answer == (
        "Pull request draft creado y verificado: "
        "https://github.com/example/repo/pull/42"
    )
    assert calls[-1] == [
        "gh",
        "pr",
        "create",
        "--draft",
        "--base",
        "main",
        "--head",
        "feature/test",
        "--title",
        "Mejora segura",
        "--body",
        "Validacion determinista",
    ]


def test_direct_explicit_pr_create_refuses_main(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        "openjarvis.speech.voice_control._repo_root",
        lambda: tmp_path,
    )

    class Result:
        returncode = 0
        stdout = "main\n"
        stderr = ""

    monkeypatch.setattr(
        "openjarvis.speech.voice_control.subprocess.run",
        lambda *args, **kwargs: Result(),
    )

    answer = _direct_explicit_pr_create(
        "crea pr con titulo No directo y descripcion Debe fallar"
    )

    assert answer == "No creo pull requests directamente desde la rama protegida main."


def test_direct_explicit_pr_create_refuses_unsynced_branch(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        "openjarvis.speech.voice_control._repo_root",
        lambda: tmp_path,
    )

    class Result:
        def __init__(self, stdout="", returncode=0):
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = ""

    responses = iter(
        [
            Result("feature/test\n"),
            Result(""),
            Result("origin/feature/test\n"),
            Result(""),
            Result("0\t1\n"),
        ]
    )
    monkeypatch.setattr(
        "openjarvis.speech.voice_control.subprocess.run",
        lambda *args, **kwargs: next(responses),
    )

    answer = _direct_explicit_pr_create(
        "crear pull request con titulo Pendiente "
        "y descripcion Falta push"
    )

    assert answer == (
        "La rama no esta sincronizada con su upstream: "
        "1 commits por enviar y 0 por recibir."
    )


def test_direct_explicit_main_sync_switches_and_fast_forwards(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        "openjarvis.speech.voice_control._repo_root",
        lambda: tmp_path,
    )
    calls: list[list[str]] = []

    class Result:
        def __init__(self, returncode=0, stdout=""):
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = ""

    responses = iter(
        [
            Result(0, ""),
            Result(0, ""),
            Result(0, ""),
            Result(0, "origin-url\n"),
            Result(0, ""),
            Result(0, ""),
            Result(0, "main\n"),
            Result(0, "abc1234\n"),
        ]
    )

    def fake_run(args, **kwargs):
        calls.append(args)
        return next(responses)

    monkeypatch.setattr(
        "openjarvis.speech.voice_control.subprocess.run",
        fake_run,
    )

    answer = _direct_explicit_main_sync("vuelve a main y actualiza")

    assert answer == (
        "Rama main activa y actualizada por fast-forward. HEAD abc1234."
    )
    assert ["git", "switch", "main"] in calls
    assert ["git", "merge", "--ff-only", "origin/main"] in calls


def test_direct_explicit_main_sync_refuses_dirty_tracked_worktree(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        "openjarvis.speech.voice_control._repo_root",
        lambda: tmp_path,
    )

    class Result:
        returncode = 0
        stdout = " M src/app.py\n"
        stderr = ""

    monkeypatch.setattr(
        "openjarvis.speech.voice_control.subprocess.run",
        lambda *args, **kwargs: Result(),
    )

    answer = _direct_explicit_main_sync("regresa a main y actualiza")

    assert answer == (
        "Hay cambios versionados pendientes. No cambie de rama para evitar "
        "perder contexto de trabajo."
    )


def test_direct_explicit_git_branch_creates_feature_from_main(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        "openjarvis.speech.voice_control._repo_root",
        lambda: tmp_path,
    )
    calls: list[list[str]] = []

    class Result:
        def __init__(self, returncode=0, stdout=""):
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = ""

    responses = iter(
        [
            Result(0, "main\n"),
            Result(0, ""),
            Result(0, ""),
            Result(1, ""),
            Result(0, ""),
            Result(0, "feature/smoke\n"),
        ]
    )

    def fake_run(args, **kwargs):
        calls.append(args)
        return next(responses)

    monkeypatch.setattr(
        "openjarvis.speech.voice_control.subprocess.run",
        fake_run,
    )

    answer = _direct_explicit_git_branch(
        "crea una rama feature/smoke desde main"
    )

    assert answer == "Rama creada y verificada: feature/smoke."
    assert ["git", "switch", "-c", "feature/smoke"] in calls


def test_direct_explicit_git_branch_refuses_non_main_base(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        "openjarvis.speech.voice_control._repo_root",
        lambda: tmp_path,
    )

    class Result:
        returncode = 0
        stdout = "feature/existing\n"
        stderr = ""

    monkeypatch.setattr(
        "openjarvis.speech.voice_control.subprocess.run",
        lambda *args, **kwargs: Result(),
    )

    answer = _direct_explicit_git_branch(
        "crea rama feature/new-one"
    )

    assert answer == (
        "Solo creo ramas nuevas desde main o master. "
        "La rama actual es feature/existing."
    )


def test_direct_explicit_git_branch_refuses_dirty_tracked_worktree(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        "openjarvis.speech.voice_control._repo_root",
        lambda: tmp_path,
    )

    class Result:
        def __init__(self, stdout=""):
            self.returncode = 0
            self.stdout = stdout
            self.stderr = ""

    responses = iter([Result("main\n"), Result(" M src/app.py\n")])
    monkeypatch.setattr(
        "openjarvis.speech.voice_control.subprocess.run",
        lambda *args, **kwargs: next(responses),
    )

    answer = _direct_explicit_git_branch(
        "crear rama fix/safe-branch"
    )

    assert answer == (
        "Hay cambios versionados pendientes. No cree la rama para evitar "
        "mezclar trabajo sin commit."
    )


def test_direct_explicit_git_push_pushes_current_feature_branch(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        "openjarvis.speech.voice_control._repo_root",
        lambda: tmp_path,
    )
    calls: list[list[str]] = []

    class Result:
        def __init__(self, returncode=0, stdout="", stderr=""):
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = stderr

    responses = iter(
        [
            Result(0, "feature/test\n"),
            Result(0, ""),
            Result(0, "https://example.invalid/repo.git\n"),
            Result(0, "", ""),
        ]
    )

    def fake_run(args, **kwargs):
        calls.append(args)
        return next(responses)

    monkeypatch.setattr(
        "openjarvis.speech.voice_control.subprocess.run",
        fake_run,
    )

    answer = _direct_explicit_git_push("haz push de la rama actual")

    assert answer == (
        "Push completado y verificado para la rama feature/test en origin."
    )
    assert calls[-1] == ["git", "push", "-u", "origin", "feature/test"]


def test_direct_explicit_git_push_refuses_main(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        "openjarvis.speech.voice_control._repo_root",
        lambda: tmp_path,
    )

    class Result:
        returncode = 0
        stdout = "main\n"
        stderr = ""

    monkeypatch.setattr(
        "openjarvis.speech.voice_control.subprocess.run",
        lambda *args, **kwargs: Result(),
    )

    answer = _direct_explicit_git_push("haz push de la rama actual")

    assert answer == "No hago push directo desde la rama protegida main."


def test_direct_explicit_git_push_refuses_dirty_tracked_worktree(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        "openjarvis.speech.voice_control._repo_root",
        lambda: tmp_path,
    )

    class Result:
        def __init__(self, stdout=""):
            self.returncode = 0
            self.stdout = stdout
            self.stderr = ""

    responses = iter([Result("feature/test\n"), Result(" M src/app.py\n")])
    monkeypatch.setattr(
        "openjarvis.speech.voice_control.subprocess.run",
        lambda *args, **kwargs: next(responses),
    )

    answer = _direct_explicit_git_push("haz push al remoto origin")

    assert answer == (
        "Hay cambios versionados sin commit. No hice push para evitar "
        "publicar una rama incompleta."
    )


def test_direct_explicit_git_commit_stages_only_tracked_changes(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        "openjarvis.speech.voice_control._repo_root",
        lambda: tmp_path,
    )
    calls: list[list[str]] = []

    class Result:
        def __init__(self, returncode=0, stdout=""):
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = ""

    responses = iter(
        [
            Result(0, ""),
            Result(0, "src/app.py\ntests/test_app.py\n"),
            Result(0, ""),
            Result(0, ""),
            Result(0, "abc1234\n"),
        ]
    )

    def fake_run(args, **kwargs):
        calls.append(args)
        return next(responses)

    monkeypatch.setattr(
        "openjarvis.speech.voice_control.subprocess.run",
        fake_run,
    )

    answer = _direct_explicit_git_commit(
        "haz un commit de los cambios versionados con mensaje mejora segura "
        "y no incluyas archivos no rastreados"
    )

    assert answer == (
        "Commit creado con 2 archivos versionados. "
        "No agregue archivos no rastreados. Commit abc1234."
    )
    assert calls[0] == ["git", "diff", "--cached", "--name-only"]
    assert calls[1] == [
        "git", "diff", "--name-only", "--diff-filter=ACDMRTUXB"
    ]
    assert calls[2] == [
        "git", "add", "-u", "--", "src/app.py", "tests/test_app.py"
    ]
    assert calls[3] == ["git", "commit", "-m", "mejora segura"]
    assert calls[4] == ["git", "rev-parse", "--short", "HEAD"]


def test_direct_explicit_git_commit_refuses_existing_staged_changes(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        "openjarvis.speech.voice_control._repo_root",
        lambda: tmp_path,
    )

    class Result:
        returncode = 0
        stdout = "src/already_staged.py\n"
        stderr = ""

    monkeypatch.setattr(
        "openjarvis.speech.voice_control.subprocess.run",
        lambda *args, **kwargs: Result(),
    )

    answer = _direct_explicit_git_commit(
        "crea un commit con mensaje no mezclar"
    )

    assert answer == (
        "Hay cambios staged previos. No cree el commit para evitar "
        "mezclar cambios existentes."
    )


def test_direct_explicit_git_commit_ignores_untracked_only_repo(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        "openjarvis.speech.voice_control._repo_root",
        lambda: tmp_path,
    )

    class Result:
        def __init__(self, stdout=""):
            self.returncode = 0
            self.stdout = stdout
            self.stderr = ""

    responses = iter([Result(""), Result("")])
    monkeypatch.setattr(
        "openjarvis.speech.voice_control.subprocess.run",
        lambda *args, **kwargs: next(responses),
    )

    answer = _direct_explicit_git_commit(
        "haz commit con mensaje solo untracked"
    )

    assert answer == "No hay cambios versionados pendientes para crear un commit."


def test_direct_explicit_pytest_runs_only_inside_tests(
    monkeypatch,
    tmp_path: Path,
) -> None:
    test_file = tmp_path / "tests" / "test_example.py"
    test_file.parent.mkdir(parents=True)
    test_file.write_text("def test_ok(): assert True\n", encoding="utf-8")
    python = tmp_path / ".venv" / "Scripts" / "python.exe"
    python.parent.mkdir(parents=True)
    python.write_text("", encoding="utf-8")

    monkeypatch.setattr(
        "openjarvis.speech.voice_control._repo_root",
        lambda: tmp_path,
    )

    calls: list[list[str]] = []

    class Result:
        returncode = 0
        stdout = "1 passed in 0.01s\n"
        stderr = ""

    def fake_run(args, **kwargs):
        calls.append(args)
        return Result()

    monkeypatch.setattr(
        "openjarvis.speech.voice_control.subprocess.run",
        fake_run,
    )

    answer = _direct_explicit_pytest(
        "ejecuta pytest tests/test_example.py -q"
    )

    assert answer == "Pruebas completadas correctamente. 1 passed in 0.01s."
    assert calls == [
        [str(python), "-m", "pytest", str(test_file.resolve()), "-q"]
    ]


def test_direct_explicit_pytest_rejects_target_outside_tests(
    monkeypatch,
    tmp_path: Path,
) -> None:
    target = tmp_path / "src" / "app.py"
    target.parent.mkdir(parents=True)
    target.write_text("print('x')\n", encoding="utf-8")
    monkeypatch.setattr(
        "openjarvis.speech.voice_control._repo_root",
        lambda: tmp_path,
    )

    answer = _direct_explicit_pytest(
        "ejecuta pytest src/app.py"
    )

    assert answer == "Solo puedo ejecutar pytest sobre rutas dentro de tests."


def test_direct_explicit_pytest_reports_failure(
    monkeypatch,
    tmp_path: Path,
) -> None:
    test_file = tmp_path / "tests" / "test_bad.py"
    test_file.parent.mkdir(parents=True)
    test_file.write_text("def test_bad(): assert False\n", encoding="utf-8")
    monkeypatch.setattr(
        "openjarvis.speech.voice_control._repo_root",
        lambda: tmp_path,
    )

    class Result:
        returncode = 1
        stdout = "1 failed in 0.02s\n"
        stderr = ""

    monkeypatch.setattr(
        "openjarvis.speech.voice_control.subprocess.run",
        lambda *args, **kwargs: Result(),
    )

    answer = _direct_explicit_pytest(
        "ejecuta pytest tests/test_bad.py"
    )

    assert answer == "Las pruebas fallaron. 1 failed in 0.02s."


def test_direct_explicit_file_delete_removes_untracked_file(
    monkeypatch,
    tmp_path: Path,
) -> None:
    target = tmp_path / ".openjarvis-smoke" / "autonomy-write.txt"
    target.parent.mkdir(parents=True)
    target.write_text("temporary", encoding="utf-8")
    monkeypatch.setattr(
        "openjarvis.speech.voice_control._repo_root",
        lambda: tmp_path,
    )

    class Result:
        returncode = 1
        stdout = ""
        stderr = ""

    monkeypatch.setattr(
        "openjarvis.speech.voice_control.subprocess.run",
        lambda *args, **kwargs: Result(),
    )

    answer = _direct_explicit_file_delete(
        "elimina el archivo .openjarvis-smoke/autonomy-write.txt "
        "y no cambies ningun otro archivo"
    )

    assert answer == "Archivo eliminado y verificado: .openjarvis-smoke/autonomy-write.txt."
    assert not target.exists()


def test_direct_explicit_file_delete_refuses_tracked_file(
    monkeypatch,
    tmp_path: Path,
) -> None:
    target = tmp_path / "README.md"
    target.write_text("tracked", encoding="utf-8")
    monkeypatch.setattr(
        "openjarvis.speech.voice_control._repo_root",
        lambda: tmp_path,
    )

    class Result:
        returncode = 0
        stdout = "README.md\n"
        stderr = ""

    monkeypatch.setattr(
        "openjarvis.speech.voice_control.subprocess.run",
        lambda *args, **kwargs: Result(),
    )

    answer = _direct_explicit_file_delete(
        "borra el archivo README.md"
    )

    assert answer == "El archivo README.md esta versionado por Git. No lo elimine."
    assert target.read_text(encoding="utf-8") == "tracked"


def test_direct_explicit_file_delete_rejects_workspace_escape(
    monkeypatch,
    tmp_path: Path,
) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-outside-delete.txt"
    outside.write_text("keep", encoding="utf-8")
    monkeypatch.setattr(
        "openjarvis.speech.voice_control._repo_root",
        lambda: tmp_path,
    )

    try:
        answer = _direct_explicit_file_delete(
            f"elimina el archivo ../{outside.name}"
        )
        assert answer == "No puedo eliminar archivos fuera del workspace de OpenJarvis."
        assert outside.read_text(encoding="utf-8") == "keep"
    finally:
        outside.unlink(missing_ok=True)


def test_direct_explicit_file_edit_updates_existing_file(
    monkeypatch,
    tmp_path: Path,
) -> None:
    target = tmp_path / ".openjarvis-smoke" / "autonomy-write.txt"
    target.parent.mkdir(parents=True)
    target.write_text("JARVIS_WRITE_OK", encoding="utf-8")
    monkeypatch.setattr(
        "openjarvis.speech.voice_control._repo_root",
        lambda: tmp_path,
    )

    answer = _direct_explicit_file_edit(
        "edita el archivo .openjarvis-smoke/autonomy-write.txt "
        "y reemplaza el contenido por JARVIS_EDIT_OK "
        "y no cambies ningun otro archivo"
    )

    assert answer == "Archivo editado y verificado: .openjarvis-smoke/autonomy-write.txt."
    assert target.read_text(encoding="utf-8") == "JARVIS_EDIT_OK"


def test_direct_explicit_file_edit_rejects_workspace_escape(
    monkeypatch,
    tmp_path: Path,
) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-outside-edit.txt"
    outside.write_text("original", encoding="utf-8")
    monkeypatch.setattr(
        "openjarvis.speech.voice_control._repo_root",
        lambda: tmp_path,
    )

    try:
        answer = _direct_explicit_file_edit(
            f"edita el archivo ../{outside.name} y reemplaza el contenido por NOPE"
        )

        assert answer == "No puedo editar archivos fuera del workspace de OpenJarvis."
        assert outside.read_text(encoding="utf-8") == "original"
    finally:
        outside.unlink(missing_ok=True)


def test_direct_explicit_file_edit_requires_existing_file(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        "openjarvis.speech.voice_control._repo_root",
        lambda: tmp_path,
    )

    answer = _direct_explicit_file_edit(
        "edita el archivo missing.txt y reemplaza el contenido por NOPE"
    )

    assert answer == "No encuentro el archivo missing.txt para editar."


def test_direct_explicit_file_write_creates_inside_workspace(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        "openjarvis.speech.voice_control._repo_root",
        lambda: tmp_path,
    )

    answer = _direct_explicit_file_write(
        "crea el archivo .openjarvis-smoke/autonomy-write.txt "
        "con el texto JARVIS_WRITE_OK y no cambies ningun otro archivo"
    )

    target = tmp_path / ".openjarvis-smoke" / "autonomy-write.txt"
    assert answer == "Archivo creado y verificado: .openjarvis-smoke/autonomy-write.txt."
    assert target.read_text(encoding="utf-8") == "JARVIS_WRITE_OK"


def test_direct_explicit_file_write_rejects_workspace_escape(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        "openjarvis.speech.voice_control._repo_root",
        lambda: tmp_path,
    )

    answer = _direct_explicit_file_write(
        "crea el archivo ../outside.txt con el texto NOPE"
    )

    assert answer == "No puedo crear archivos fuera del workspace de OpenJarvis."
    assert not (tmp_path.parent / "outside.txt").exists()


def test_direct_explicit_file_write_does_not_overwrite(
    monkeypatch,
    tmp_path: Path,
) -> None:
    target = tmp_path / "existing.txt"
    target.write_text("original", encoding="utf-8")
    monkeypatch.setattr(
        "openjarvis.speech.voice_control._repo_root",
        lambda: tmp_path,
    )

    answer = _direct_explicit_file_write(
        "crea el archivo existing.txt con el texto reemplazo"
    )

    assert answer == "El archivo existing.txt ya existe. No lo sobrescribi."
    assert target.read_text(encoding="utf-8") == "original"


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


def test_direct_lists_project_for_natural_directory_phrase(
    monkeypatch,
    tmp_path: Path,
) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "README.md").write_text("ok", encoding="utf-8")
    monkeypatch.setattr(
        "openjarvis.speech.voice_control._repo_root",
        lambda: tmp_path,
    )

    answer = direct("lista el contenido del directorio del proyecto")

    assert answer == "Archivos y carpetas principales: README.md, src."


def test_direct_reviews_repository_without_modifying_files(monkeypatch) -> None:
    class Result:
        returncode = 0
        stdout = " M src/app.py\n?? scratch.txt\n?? notes.md\n"

    monkeypatch.setattr(
        "openjarvis.speech.voice_control.subprocess.run",
        lambda *args, **kwargs: Result(),
    )

    answer = direct(
        "revisa el estado del repositorio, identifica archivos modificados "
        "y resume si hay algo pendiente sin cambiar archivos"
    )

    assert answer == (
        "Repositorio revisado sin modificar archivos. Hay "
        "1 archivo versionado modificado y 2 archivos no rastreados. "
        "Pendientes: src/app.py, scratch.txt, notes.md."
    )


def test_direct_git_diff_summary_reports_tracked_changes(monkeypatch) -> None:
    class Result:
        returncode = 0
        stdout = "M\tsrc/app.py\nA\ttests/test_new.py\n"
        stderr = ""

    monkeypatch.setattr(
        "openjarvis.speech.voice_control.subprocess.run",
        lambda *args, **kwargs: Result(),
    )

    answer = direct("revisa el diff")

    assert answer == (
        "Git tiene diferencias en 2 archivos versionados: "
        "src/app.py (modificado), tests/test_new.py (agregado)."
    )


def test_direct_git_diff_summary_reports_clean(monkeypatch) -> None:
    class Result:
        returncode = 0
        stdout = ""
        stderr = ""

    monkeypatch.setattr(
        "openjarvis.speech.voice_control.subprocess.run",
        lambda *args, **kwargs: Result(),
    )

    answer = direct("resume los cambios git")

    assert answer == "No hay diferencias versionadas pendientes en Git."


def test_direct_git_status_separates_tracked_and_untracked(monkeypatch) -> None:
    class Result:
        returncode = 0
        stdout = " M src/app.py\n?? scratch.txt\n?? notes.md\n"

    monkeypatch.setattr(
        "openjarvis.speech.voice_control.subprocess.run",
        lambda *args, **kwargs: Result(),
    )

    answer = direct("revisa el estado git del proyecto")

    assert answer == "Git tiene 1 cambios versionados y 2 archivos no rastreados."


def test_direct_voice_help_lists_capabilities() -> None:
    answer = direct("que puedes hacer")

    assert answer is not None
    assert "Docker" in answer
    assert "prepara la rama actual para pull request" in answer
    assert "finaliza el pr actual" in answer


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
    assert calls[0][1]["config"]["model"] == AUTONOMY_MODEL
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
