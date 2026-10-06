from __future__ import annotations

from pathlib import Path

from openjarvis.speech.voice_control import _requires_tool_evidence, direct, wake_command


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
