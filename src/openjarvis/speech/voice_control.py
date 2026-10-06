"""Native always-on voice control for OpenJarvis."""

from __future__ import annotations

import array
import difflib
import io
import json
import logging
import os
import re
import subprocess
import sys
import time
import types
import unicodedata
import urllib.request
import wave
import webbrowser
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from openjarvis.core.config import load_config
from openjarvis.speech._discovery import get_speech_backend
from openjarvis.speech.voice_io import record_until_silence, resolve_input_sample_rate

HOME = Path.home() / ".openjarvis"
LOG_PATH = HOME / "voice-control.log"
STATE_PATH = HOME / "voice-control.json"
STOP_PATH = HOME / "voice-control.stop"
API_BASE = os.environ.get("OPENJARVIS_VOICE_API", "http://127.0.0.1:8000")
MODEL = os.environ.get("OPENJARVIS_VOICE_MODEL", "qwen3.5:4b")
VOICE_AGENT_NAME = os.environ.get("OPENJARVIS_VOICE_AGENT", "Jarvis Voice Operator V2")
THRESHOLD = int(os.environ.get("OPENJARVIS_VOICE_THRESHOLD", "180"))
WAKE_THRESHOLD = float(os.environ.get("OPENJARVIS_WAKE_THRESHOLD", "0.18"))
WAKE_MODE = os.environ.get("OPENJARVIS_WAKE_MODE", "auto").strip().lower()
WAKE_MODEL_DIR = HOME / "models" / "openwakeword"
AUDIO_DEVICE = os.environ.get("OPENJARVIS_AUDIO_DEVICE", "wasapi-default").strip()
WAKE_ALIASES = (
    "jarvis",
    "yarvis",
    "charvis",
    "jarbis",
    "arvis",
    "arbis",
    "harvis",
    "ya hareis",
    "ya jaris",
    "ya harvis",
)

HOME.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    filename=LOG_PATH,
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    encoding="utf-8",
)
log = logging.getLogger("openjarvis.voice")


def state(name: str, **extra: Any) -> None:
    payload = {
        "state": name,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        **extra,
    }
    tmp = STATE_PATH.with_name(f"{STATE_PATH.stem}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    for attempt in range(5):
        try:
            tmp.replace(STATE_PATH)
            return
        except PermissionError:
            if attempt == 4:
                log.warning("Could not publish voice state after retries: %s", STATE_PATH)
                tmp.unlink(missing_ok=True)
                return
            time.sleep(0.05 * (attempt + 1))


def normalize(text: str) -> str:
    raw = unicodedata.normalize("NFKD", text.casefold())
    raw = "".join(ch for ch in raw if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", raw).strip()


def _clean_voice_command(text: str) -> str:
    return text.strip().strip(" ,.:;!?¿¡")


def wake_command(text: str) -> tuple[bool, str]:
    n = normalize(text)
    for alias in WAKE_ALIASES:
        m = re.search(r"\b" + re.escape(alias) + r"\b[\s,:;.-]*(.*)$", n)
        if m:
            return True, _clean_voice_command(m.group(1))

    # Whisper can render the wake word phonetically (for example "Arbis").
    # Accept only close 4-7 character tokens near the start of the utterance.
    tokens = re.findall(r"[a-z0-9]+", n)
    for index, token in enumerate(tokens[:3]):
        if 4 <= len(token) <= 7:
            score = difflib.SequenceMatcher(None, token, "jarvis").ratio()
            if score >= 0.70:
                return True, " ".join(tokens[index + 1 :]).strip()
    return False, ""


def resolve_audio_device() -> int | str | None:
    """Resolve the input device used by native voice control."""
    value = AUDIO_DEVICE
    if not value:
        return None
    if value.isdigit():
        return int(value)
    if value.casefold() != "wasapi-default":
        return value

    try:
        import sounddevice as sd

        for host in sd.query_hostapis():
            if "wasapi" in str(host.get("name", "")).casefold():
                index = int(host.get("default_input_device", -1))
                return index if index >= 0 else None
    except Exception as exc:
        log.warning("Could not resolve WASAPI input device: %s", exc)
    return None


def wav_rms(audio: bytes) -> float:
    try:
        with wave.open(io.BytesIO(audio), "rb") as wf:
            samples = array.array("h")
            samples.frombytes(wf.readframes(wf.getnframes()))
    except Exception:
        return 0.0
    if not samples:
        return 0.0
    return (sum(sample * sample for sample in samples) / len(samples)) ** 0.5


def api(path: str, payload: dict[str, Any] | None = None, timeout: float = 120) -> Any:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(
        API_BASE + path,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST" if data else "GET",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def speak(text: str) -> None:
    text = re.sub(r"[`*_#>]+", "", text)
    text = re.sub(r"\s+", " ", text).strip()[:700]
    if not text:
        return
    safe = text.replace("'", "''")
    ps = (
        "Add-Type -AssemblyName System.Speech; "
        "$s=New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        "$s.Rate=0; $s.Speak('" + safe + "')"
    )
    subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", ps],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=90,
        check=False,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


def _repo_root() -> Path:
    configured = os.environ.get("OPENJARVIS_VOICE_REPO", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(__file__).resolve().parents[3]


def _extract_local_path(command: str) -> Path | None:
    # Preserve the original command here: normalize() removes accents but paths
    # and Windows separators must remain untouched.
    drive_match = re.search(r"([A-Za-z]:\\[^\r\n]+)", command)
    if drive_match:
        raw = drive_match.group(1).strip().strip("\"'").rstrip(".,;")
        return Path(raw)

    n = normalize(command)
    repo = _repo_root()
    known_files = {
        "pyproject.toml": repo / "pyproject.toml",
        "uv.lock": repo / "uv.lock",
        "readme": repo / "README.md",
        "readme.md": repo / "README.md",
    }
    for spoken_name, path in known_files.items():
        if spoken_name in n:
            return path
    return None


def _format_bytes(size: int) -> str:
    if size < 1024:
        return f"{size} bytes"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} kilobytes"
    return f"{size / (1024 * 1024):.1f} megabytes"


def direct(command: str) -> str | None:
    n = normalize(command)
    if "abre dashboard" in n or "abre el panel" in n or "abre panel" in n:
        webbrowser.open("http://127.0.0.1:5173/dashboard")
        return "Abriendo el panel de Jarvis."
    if "abre agentes" in n or "abre los agentes" in n:
        webbrowser.open("http://127.0.0.1:5173/agents")
        return "Abriendo agentes."
    if "abre chat" in n or "abre el chat" in n:
        webbrowser.open("http://127.0.0.1:5173/")
        return "Abriendo el chat."

    local_path = _extract_local_path(command)
    if local_path is not None and any(
        phrase in n
        for phrase in (
            "tamano del archivo",
            "cuanto pesa el archivo",
            "informacion del archivo",
            "info del archivo",
        )
    ):
        if not local_path.exists():
            return f"No encuentro el archivo {local_path.name}."
        if not local_path.is_file():
            return f"{local_path.name} no es un archivo."
        size = _format_bytes(local_path.stat().st_size)
        return f"El archivo {local_path.name} tiene {size}."

    if local_path is not None and any(
        phrase in n
        for phrase in ("existe el archivo", "esta el archivo", "encuentra el archivo")
    ):
        return (
            f"Si. El archivo {local_path.name} existe."
            if local_path.exists()
            else f"No. El archivo {local_path.name} no existe."
        )

    if "estado git" in n or "git status" in n:
        repo = _repo_root()
        proc = subprocess.run(
            ["git", "status", "--short"],
            cwd=repo,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if proc.returncode != 0:
            return "No pude consultar el estado de Git."
        changes = [line for line in proc.stdout.splitlines() if line.strip()]
        if not changes:
            return "Git esta limpio. No hay cambios locales."
        return f"Git tiene {len(changes)} cambios locales."

    if any(
        phrase in n
        for phrase in ("lista archivos del proyecto", "lista los archivos del proyecto")
    ):
        repo = _repo_root()
        names = sorted(
            path.name for path in repo.iterdir() if not path.name.startswith(".")
        )
        preview = ", ".join(names[:12])
        suffix = "" if len(names) <= 12 else f", y {len(names) - 12} mas"
        return f"Archivos y carpetas principales: {preview}{suffix}."

    if "estado del sistema" in n or "estado de jarvis" in n:
        s = api("/v1/operations/status", timeout=10)
        r, e, m, t = (
            s.get("runtime", {}),
            s.get("execution", {}),
            s.get("memory", {}),
            s.get("tools", {}),
        )
        machine = s.get("machines", {}).get("selected") or "trabajo"
        return (
            f"Jarvis operativo. Modelo {r.get('model') or MODEL}, maquina {machine}, "
            "Commander "
            f"{'conectado' if e.get('commander_connected') else 'desconectado'}, "
            f"memoria {'activa' if m.get('enabled') else 'inactiva'}, "
            f"{t.get('mcp_count', 0)} herramientas M C P disponibles."
        )
    if "prueba de voz" in n or "test de voz" in n:
        return "Te escucho correctamente. El control de voz de Jarvis esta operativo."
    return None


def chat(command: str) -> str:
    """Local fallback that talks directly to Ollama, never to a cloud engine."""
    payload = {
        "model": MODEL,
        "stream": False,
        "messages": [
            {
                "role": "system",
                "content": (
                    "Eres Jarvis. Responde en espanol, breve y orientado a "
                    "ejecucion."
                ),
            },
            {"role": "user", "content": command},
        ],
        "options": {"temperature": 0.2, "num_predict": 300},
    }
    req = urllib.request.Request(
        "http://127.0.0.1:11434/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        response = json.loads(resp.read().decode("utf-8"))
    return str((response.get("message") or {}).get("content") or "").strip()


def _voice_agent_id() -> str | None:
    try:
        payload = api("/v1/managed-agents", timeout=10)
    except Exception:
        return None
    agents = payload.get("agents", [])
    for agent in agents:
        if str(agent.get("name", "")).strip() == VOICE_AGENT_NAME:
            return str(agent.get("id") or "") or None
    for agent in agents:
        if str(agent.get("name", "")).strip().casefold().startswith(
            "jarvis voice operator"
        ):
            return str(agent.get("id") or "") or None
    return None


def managed(command: str) -> str:
    """Run a voice command through the governed managed-agent plane."""
    agent_id = _voice_agent_id()
    if not agent_id:
        raise RuntimeError(f"Managed voice agent {VOICE_AGENT_NAME!r} was not found")

    sent = api(
        f"/v1/managed-agents/{agent_id}/messages",
        {"content": command, "mode": "queued", "stream": False},
        timeout=15,
    )
    sent_at = float(sent.get("created_at") or time.time())
    api(
        f"/v1/managed-agents/{agent_id}/run",
        {},
        timeout=15,
    )

    deadline = time.monotonic() + 150
    while time.monotonic() < deadline:
        messages = api(
            f"/v1/managed-agents/{agent_id}/messages",
            timeout=10,
        ).get("messages", [])
        for message in messages:
            created_at = float(message.get("created_at") or 0.0)
            if message.get("direction") == "agent_to_user" and created_at >= sent_at:
                content = str(message.get("content") or "").strip()
                if content:
                    return content

        agent = api(f"/v1/managed-agents/{agent_id}", timeout=10)
        status = str(agent.get("status") or "")
        if status in {"error", "needs_attention"}:
            detail = str(agent.get("summary_memory") or "").strip()
            raise RuntimeError(detail or f"Voice agent ended in state {status}")
        time.sleep(1.0)

    raise TimeoutError("El agente de voz excedio el tiempo de respuesta.")


def execute(command: str) -> str:
    answer = direct(command)
    if answer is not None:
        return answer
    try:
        return managed(command)
    except Exception as exc:
        log.warning("Managed voice execution failed, falling back to chat: %s", exc)
        return chat(command)


def load_wake_detector():
    try:
        # openWakeWord imports an optional custom-verifier trainer that pulls
        # scikit-learn. Windows Application Control blocks that optional DLL on
        # this machine, so stub only the unused training module before import.
        if "openwakeword.custom_verifier_model" not in sys.modules:
            stub = types.ModuleType("openwakeword.custom_verifier_model")

            def _unavailable(*args, **kwargs):
                raise RuntimeError("Custom wake-word verifier training is unavailable")

            stub.train_custom_verifier = _unavailable
            sys.modules["openwakeword.custom_verifier_model"] = stub

        from openwakeword.model import Model

        mel = WAKE_MODEL_DIR / "melspectrogram.onnx"
        emb = WAKE_MODEL_DIR / "embedding_model.onnx"
        wake = WAKE_MODEL_DIR / "hey_jarvis_v0.1.onnx"
        if not all(path.exists() for path in (mel, emb, wake)):
            return None

        return Model(
            wakeword_models=[str(wake)],
            inference_framework="onnx",
            melspec_model_path=str(mel),
            embedding_model_path=str(emb),
        )
    except Exception as exc:
        log.warning("Wake detector unavailable: %s", exc)
        return None


def wait_for_wake(detector) -> float | None:
    import numpy as np
    import sounddevice as sd

    detector.reset()
    last_state = 0.0
    device = resolve_audio_device()
    input_rate = resolve_input_sample_rate(
        requested_rate=16000,
        device=device,
    )
    source_block = max(1, round(input_rate * 1280 / 16000))
    with sd.RawInputStream(
        samplerate=input_rate,
        channels=1,
        dtype="int16",
        blocksize=source_block,
        device=device,
    ) as stream:
        while not STOP_PATH.exists():
            raw, _ = stream.read(source_block)
            frame = np.frombuffer(bytes(raw), dtype=np.int16)
            if input_rate != 16000:
                target_positions = np.linspace(
                    0,
                    len(frame) - 1,
                    1280,
                )
                frame = np.interp(
                    target_positions,
                    np.arange(len(frame)),
                    frame,
                ).astype(np.int16)
            prediction = detector.predict(frame)
            score = max((float(np.max(v)) for v in prediction.values()), default=0.0)
            now = time.monotonic()
            if now - last_state >= 1.0:
                state(
                    "listening",
                    wake_word="Hey Jarvis",
                    wake_score=round(score, 4),
                    audio_device=device,
                    sample_rate=input_rate,
                )
                last_state = now
            if score >= WAKE_THRESHOLD:
                log.info("Wake detected score=%.4f", score)
                return score
    return None


def capture_command(backend) -> str:
    state("awake", wake_word="Hey Jarvis")
    speak("Te escucho.")
    audio = record_until_silence(
        silence_threshold=THRESHOLD,
        silence_seconds=0.9,
        startup_silence_seconds=6.0,
        max_seconds=20.0,
        device=resolve_audio_device(),
    )
    amplitude = wav_rms(audio)
    if amplitude < max(20.0, THRESHOLD * 0.35):
        state("ready", note="no-command-heard")
        return ""
    state("transcribing", level=round(amplitude, 2))
    text = backend.transcribe(audio, format="wav", language="es").text.strip()
    if text:
        log.info("Command transcript: %s", text)
    return text


def fallback_command(backend) -> str:
    state("listening", wake_word="Jarvis", mode="whisper-fallback")
    audio = record_until_silence(
        silence_threshold=THRESHOLD,
        silence_seconds=0.9,
        startup_silence_seconds=2.5,
        max_seconds=18.0,
        device=resolve_audio_device(),
    )
    amplitude = wav_rms(audio)
    if amplitude < max(40.0, THRESHOLD * 0.60):
        log.debug("Fallback ignored low-level audio rms=%.1f threshold=%s", amplitude, THRESHOLD)
        return ""
    heard = backend.transcribe(audio, format="wav", language="es").text.strip()
    log.info("Fallback heard rms=%.1f transcript=%r", amplitude, heard)
    if not heard:
        return ""
    woke, command = wake_command(heard)
    if not woke:
        return ""
    if command:
        return command
    speak("Te escucho.")
    return capture_command(backend)


def main() -> int:
    STOP_PATH.unlink(missing_ok=True)
    backend = get_speech_backend(load_config())
    if backend is None:
        state("error", error="speech-backend-unavailable")
        return 2

    detector = None if WAKE_MODE == "whisper-fallback" else load_wake_detector()
    wake_mode = "openwakeword" if detector is not None else "whisper-fallback"
    audio_device = resolve_audio_device()
    log.info(
        "Voice control started backend=%s threshold=%s wake_mode=%s audio_device=%s",
        getattr(backend, "backend_id", "?"),
        THRESHOLD,
        wake_mode,
        audio_device,
    )
    state(
        "ready",
        backend=getattr(backend, "backend_id", "unknown"),
        wake_word="Hey Jarvis" if detector is not None else "Jarvis",
        wake_mode=wake_mode,
        audio_device=audio_device,
    )

    while not STOP_PATH.exists():
        try:
            if detector is not None:
                score = wait_for_wake(detector)
                if score is None:
                    break
                state("wake-detected", wake_score=round(score, 4))
                command = capture_command(backend)
            else:
                command = fallback_command(backend)

            command = command.strip()
            if not command:
                continue

            n = normalize(command)
            if n in {
                "deja de escuchar",
                "detener escucha",
                "apaga el control de voz",
                "silencio",
            }:
                state("stopped", command=command)
                speak("Control de voz detenido.")
                return 0

            state("processing", command=command)
            log.info("Command: %s", command)
            answer = execute(command)
            log.info("Answer: %s", answer)
            state("speaking", command=command, answer=answer)
            speak(answer)
            state(
                "ready", last_command=command, last_answer=answer, wake_mode=wake_mode
            )
        except KeyboardInterrupt:
            break
        except Exception as exc:
            log.exception("Voice loop error")
            state("error", error=str(exc), wake_mode=wake_mode)
            time.sleep(1.0)

    state("stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
