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

HOME = Path.home() / ".openjarvis"


def record_until_silence(*args, **kwargs):
    from openjarvis.speech.voice_io import record_until_silence as _record

    return _record(*args, **kwargs)


def resolve_input_sample_rate(*args, **kwargs):
    from openjarvis.speech.voice_io import resolve_input_sample_rate as _resolve

    return _resolve(*args, **kwargs)

LOG_PATH = HOME / "voice-control.log"
STATE_PATH = HOME / "voice-control.json"
STOP_PATH = HOME / "voice-control.stop"
API_BASE = os.environ.get("OPENJARVIS_VOICE_API", "http://127.0.0.1:8000")
MODEL = os.environ.get("OPENJARVIS_VOICE_MODEL", "qwen3.5:4b")
AUTONOMY_MODEL = os.environ.get("OPENJARVIS_AUTONOMY_MODEL", MODEL)
VOICE_AGENT_NAME = os.environ.get("OPENJARVIS_VOICE_AGENT", "Jarvis Voice Operator V2")
AUTONOMY_AGENT_NAME = os.environ.get(
    "OPENJARVIS_AUTONOMY_AGENT",
    "Jarvis Autonomous Operator",
)
THRESHOLD = int(os.environ.get("OPENJARVIS_VOICE_THRESHOLD", "180"))
WAKE_THRESHOLD = float(os.environ.get("OPENJARVIS_WAKE_THRESHOLD", "0.18"))
SHORT_WAKE_THRESHOLD = float(os.environ.get("OPENJARVIS_SHORT_WAKE_THRESHOLD", "0.008"))
SHORT_WAKE_RMS = float(os.environ.get("OPENJARVIS_SHORT_WAKE_RMS", "100"))
WAKE_MODE = os.environ.get("OPENJARVIS_WAKE_MODE", "whisper-fallback").strip().lower()
WAKE_MODEL_DIR = HOME / "models" / "openwakeword"
AUDIO_DEVICE = os.environ.get("OPENJARVIS_AUDIO_DEVICE", "wasapi-default").strip()
WAKE_ALIASES = (
    "jarvis",
    "yarvis",
    "charvis",
    "jarbis",
    "arvis",
    "arbis",
    "arbiz",
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
_INSTANCE_MUTEX: Any | None = None


class UnverifiedVoiceActionError(RuntimeError):
    """Raised when an action-like request has no real tool evidence."""


def _requires_tool_evidence(command: str) -> bool:
    n = normalize(command)
    action_terms = (
        "abre ",
        "abrir ",
        "ejecuta ",
        "ejecutar ",
        "verifica ",
        "verificar ",
        "consulta ",
        "consultar ",
        "lista ",
        "listar ",
        "cambia ",
        "cambiar ",
        "crea ",
        "crear ",
        "elimina ",
        "eliminar ",
        "borra ",
        "borrar ",
        "guarda ",
        "guardar ",
        "haz ",
        "hacer ",
        "inicia ",
        "iniciar ",
        "deten ",
        "detener ",
        "reinicia ",
        "reiniciar ",
        "instala ",
        "instalar ",
        "actualiza ",
        "actualizar ",
        "descarga ",
        "descargar ",
        "sube ",
        "subir ",
        "implementa ",
        "implementar ",
        "desarrolla ",
        "desarrollar ",
        "corrige ",
        "corregir ",
        "revisa ",
        "revisar ",
        "continua ",
        "continuar ",
        "optimiza ",
        "optimizar ",
        "migra ",
        "migrar ",
        "commit",
        "push",
        "pull",
        "docker ",
        "git ",
    )
    return any(term in n for term in action_terms)


def _is_autonomous_objective(command: str) -> bool:
    """Return True only for explicit, actionable autonomous objectives."""
    n = normalize(command)
    if len(n) < 12:
        return False
    if n.startswith(("que ", "como ", "cuando ", "donde ", "por que ", "cual ")):
        return False
    if any(
        phrase in n
        for phrase in (
            "estado autonomo",
            "estado de autonomia",
            "deten trabajo autonomo",
            "detener trabajo autonomo",
            "pausa trabajo autonomo",
            "reanuda trabajo autonomo",
            "reanudar trabajo autonomo",
        )
    ):
        return False
    imperative_terms = (
        "implementa ",
        "implementar ",
        "desarrolla ",
        "desarrollar ",
        "corrige ",
        "corregir ",
        "revisa ",
        "revisar ",
        "continua ",
        "continuar ",
        "optimiza ",
        "optimizar ",
        "migra ",
        "migrar ",
        "ejecuta ",
        "ejecutar ",
        "verifica ",
        "verificar ",
        "lista ",
        "listar ",
        "crea ",
        "crear ",
        "actualiza ",
        "actualizar ",
        "instala ",
        "instalar ",
        "haz ",
        "hacer ",
        "commit",
        "push",
        "pull",
    )
    return any(term in n for term in imperative_terms)


def acquire_single_instance() -> bool:
    """Allow only one native voice listener per Windows session."""
    global _INSTANCE_MUTEX
    if os.name != "nt":
        return True
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.CreateMutexW(None, False, "Local\\OpenJarvisVoiceControl")
        if not handle:
            return True
        _INSTANCE_MUTEX = handle
        return kernel32.GetLastError() != 183  # ERROR_ALREADY_EXISTS
    except Exception as exc:
        log.warning("Could not create single-instance voice mutex: %s", exc)
        return True


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
                log.warning(
                    "Could not publish voice state after retries: %s", STATE_PATH
                )
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


def audio_device_candidates() -> list[int | str | None]:
    """Return ordered input-device candidates for resilient voice capture."""
    try:
        import sounddevice as sd
    except Exception as exc:
        log.warning("Could not inspect audio devices: %s", exc)
        return [None]

    candidates: list[int | str | None] = []

    def add(device: int | str | None) -> None:
        if device is not None and device not in candidates:
            candidates.append(device)

    value = AUDIO_DEVICE
    if value:
        if value.isdigit():
            add(int(value))
        elif value.casefold() in {"default", "system-default"}:
            try:
                index = int(sd.default.device[0])
                if index >= 0:
                    add(index)
            except Exception as exc:
                log.warning("Could not resolve system default input device: %s", exc)
        elif value.casefold() == "wasapi-default":
            try:
                for host in sd.query_hostapis():
                    if "wasapi" in str(host.get("name", "")).casefold():
                        index = int(host.get("default_input_device", -1))
                        if index >= 0:
                            add(index)
            except Exception as exc:
                log.warning("Could not resolve WASAPI input device: %s", exc)
        else:
            add(value)

    try:
        index = int(sd.default.device[0])
        if index >= 0:
            add(index)
    except Exception as exc:
        log.debug("Could not add system default input candidate: %s", exc)

    try:
        for index, info in enumerate(sd.query_devices()):
            if int(info.get("max_input_channels", 0)) > 0:
                add(index)
    except Exception as exc:
        log.debug("Could not enumerate input devices: %s", exc)

    if not candidates:
        candidates.append(None)
    return candidates


def resolve_audio_device() -> int | str | None:
    """Resolve the preferred input device used by native voice control."""
    return audio_device_candidates()[0]


def record_voice_audio(**kwargs: Any) -> bytes:
    """Capture audio, failing over across available input devices."""
    last_error: Exception | None = None
    for device in audio_device_candidates():
        try:
            return record_until_silence(device=device, **kwargs)
        except Exception as exc:
            last_error = exc
            log.warning("Voice capture failed on device %r: %s", device, exc)
    if last_error is not None:
        raise last_error
    return record_until_silence(device=None, **kwargs)


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


def api(
    path: str,
    payload: dict[str, Any] | None = None,
    timeout: float = 120,
    method: str | None = None,
) -> Any:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    http_method = method or ("POST" if data else "GET")
    req = urllib.request.Request(
        API_BASE + path,
        data=data,
        headers={"Content-Type": "application/json"},
        method=http_method,
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _api_healthy(timeout: float = 2.0) -> bool:
    try:
        with urllib.request.urlopen(API_BASE + "/health", timeout=timeout) as resp:
            return 200 <= int(getattr(resp, "status", 200)) < 500
    except Exception:
        return False


def _ensure_api_available(timeout_seconds: float = 25.0) -> bool:
    """Recover the local OpenJarvis API once before autonomous work starts."""
    if _api_healthy():
        return True

    repo = _repo_root()
    python = repo / ".venv" / "Scripts" / "python.exe"
    if not python.exists():
        python = Path(sys.executable)

    common = {
        "cwd": repo,
        "capture_output": True,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
        "check": False,
        "creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0),
    }
    try:
        subprocess.run(
            [str(python), "-m", "openjarvis.cli", "stop"],
            timeout=20,
            **common,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        log.warning("Could not stop unhealthy OpenJarvis API cleanly: %s", exc)

    try:
        subprocess.Popen(
            [
                str(python),
                "-m",
                "openjarvis.cli",
                "start",
                "--host",
                "127.0.0.1",
                "--port",
                "8000",
                "--engine",
                "ollama",
                "--model",
                MODEL,
                "--agent",
                "orchestrator",
            ],
            cwd=repo,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except OSError as exc:
        log.warning("Could not restart OpenJarvis API: %s", exc)
        return False

    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if _api_healthy():
            return True
        time.sleep(0.25)
    return False


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


def _open_windows_app(command: str) -> str | None:
    if os.name != "nt":
        return None
    n = normalize(command)
    apps = (
        (
            ("abre visual studio code", "abre vscode", "abre code"),
            ["cmd.exe", "/c", "start", "", "code"],
            "Visual Studio Code",
        ),
        (
            ("abre explorador", "abre el explorador"),
            ["explorer.exe"],
            "el Explorador de archivos",
        ),
        (("abre powershell", "abre power shell"), ["powershell.exe"], "PowerShell"),
        (
            ("abre docker desktop", "abre docker"),
            [r"C:\Program Files\Docker\Docker\Docker Desktop.exe"],
            "Docker Desktop",
        ),
        (
            ("abre chrome", "abre google chrome"),
            ["cmd.exe", "/c", "start", "", "chrome"],
            "Google Chrome",
        ),
    )
    for phrases, argv, label in apps:
        if any(phrase in n for phrase in phrases):
            try:
                subprocess.Popen(
                    argv,
                    cwd=_repo_root(),
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
                )
            except Exception as exc:
                log.warning("Could not open %s: %s", label, exc)
                return f"No pude abrir {label}."
            return f"Abriendo {label}."
    return None


def _direct_explicit_file_write(command: str) -> str | None:
    match = re.search(
        r"(?is)\bcrea(?:r)?\s+el\s+archivo\s+(.+?)\s+con\s+el\s+texto\s+(.+)$",
        command.strip(),
    )
    if match is None:
        return None

    raw_path = match.group(1).strip().strip("\"'")
    content = match.group(2).strip()
    content = re.sub(
        r"(?is)\s+y\s+no\s+cambies\s+ningun\s+otro\s+archivo\s*$",
        "",
        content,
    ).strip()
    content = content.strip("\"'")

    if not raw_path or not content:
        return "Necesito una ruta y un texto explicitos para crear el archivo."

    repo = _repo_root().resolve()
    candidate = Path(raw_path)
    target = candidate.resolve() if candidate.is_absolute() else (repo / candidate).resolve()

    try:
        relative = target.relative_to(repo)
    except ValueError:
        return "No puedo crear archivos fuera del workspace de OpenJarvis."

    if target.exists():
        return f"El archivo {relative.as_posix()} ya existe. No lo sobrescribi."

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    verified = target.read_text(encoding="utf-8")
    if verified != content:
        target.unlink(missing_ok=True)
        return "No pude verificar el contenido escrito; reverti el archivo temporal."

    return f"Archivo creado y verificado: {relative.as_posix()}."


def _direct_explicit_file_edit(command: str) -> str | None:
    match = re.search(
        r"(?is)\b(?:edita|editar|modifica|modificar)\s+el\s+archivo\s+(.+?)\s+"
        r"(?:y\s+)?(?:reemplaza|reemplazar|cambia|cambiar)\s+"
        r"(?:el\s+)?contenido\s+(?:por|con)\s+(.+)$",
        command.strip(),
    )
    if match is None:
        return None

    raw_path = match.group(1).strip().strip("\"'")
    content = match.group(2).strip()
    content = re.sub(
        r"(?is)\s+y\s+no\s+cambies\s+ningun\s+otro\s+archivo\s*$",
        "",
        content,
    ).strip()
    content = content.strip("\"'")

    if not raw_path or not content:
        return "Necesito una ruta y un contenido explicitos para editar el archivo."

    repo = _repo_root().resolve()
    candidate = Path(raw_path)
    target = candidate.resolve() if candidate.is_absolute() else (repo / candidate).resolve()

    try:
        relative = target.relative_to(repo)
    except ValueError:
        return "No puedo editar archivos fuera del workspace de OpenJarvis."

    if not target.exists() or not target.is_file():
        return f"No encuentro el archivo {relative.as_posix()} para editar."

    original = target.read_text(encoding="utf-8")
    try:
        target.write_text(content, encoding="utf-8")
        verified = target.read_text(encoding="utf-8")
    except Exception:
        target.write_text(original, encoding="utf-8")
        raise

    if verified != content:
        target.write_text(original, encoding="utf-8")
        return "No pude verificar la edicion; restaure el contenido original."

    return f"Archivo editado y verificado: {relative.as_posix()}."


def _direct_explicit_file_delete(command: str) -> str | None:
    match = re.search(
        r"(?is)\b(?:elimina|eliminar|borra|borrar)\s+el\s+archivo\s+(.+)$",
        command.strip(),
    )
    if match is None:
        return None

    raw_path = match.group(1).strip()
    raw_path = re.sub(
        r"(?is)\s+y\s+no\s+cambies\s+ningun\s+otro\s+archivo\s*$",
        "",
        raw_path,
    ).strip().strip("\"'")

    if not raw_path:
        return "Necesito una ruta explicita para eliminar el archivo."

    repo = _repo_root().resolve()
    candidate = Path(raw_path)
    target = candidate.resolve() if candidate.is_absolute() else (repo / candidate).resolve()

    try:
        relative = target.relative_to(repo)
    except ValueError:
        return "No puedo eliminar archivos fuera del workspace de OpenJarvis."

    if not target.exists():
        return f"No encuentro el archivo {relative.as_posix()} para eliminar."
    if not target.is_file():
        return f"{relative.as_posix()} no es un archivo; no lo elimine."

    proc = subprocess.run(
        ["git", "ls-files", "--error-unmatch", "--", relative.as_posix()],
        cwd=repo,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=10,
        check=False,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if proc.returncode == 0:
        return (
            f"El archivo {relative.as_posix()} esta versionado por Git. "
            "No lo elimine."
        )
    if proc.returncode != 1:
        return (
            "No pude verificar de forma segura si el archivo esta versionado; "
            "no lo elimine."
        )

    target.unlink()
    if target.exists():
        return "No pude verificar la eliminacion del archivo."
    return f"Archivo eliminado y verificado: {relative.as_posix()}."


def _direct_explicit_pytest(command: str) -> str | None:
    match = re.search(
        r"(?is)\bpytest\s+(\"[^\"]+\"|'[^']+'|\S+)",
        command.strip(),
    )
    if match is None:
        return None

    raw_target = match.group(1).strip().strip("\"'")
    if not raw_target:
        return "Necesito una ruta de pruebas explicita."

    repo = _repo_root().resolve()
    node_parts = raw_target.split("::")
    target_path = Path(node_parts[0])
    resolved = (
        target_path.resolve()
        if target_path.is_absolute()
        else (repo / target_path).resolve()
    )
    tests_root = (repo / "tests").resolve()

    try:
        relative = resolved.relative_to(tests_root)
    except ValueError:
        return "Solo puedo ejecutar pytest sobre rutas dentro de tests."

    if not resolved.exists():
        return f"No encuentro la prueba tests/{relative.as_posix()}."

    target_arg = str(resolved)
    if len(node_parts) > 1:
        target_arg += "::" + "::".join(node_parts[1:])

    python = repo / ".venv" / "Scripts" / "python.exe"
    if not python.exists():
        python = Path(sys.executable)

    try:
        proc = subprocess.run(
            [str(python), "-m", "pytest", target_arg, "-q"],
            cwd=repo,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except subprocess.TimeoutExpired:
        return "Pytest excedio el tiempo maximo de ejecucion."

    output = "\n".join(
        part.strip()
        for part in (proc.stdout, proc.stderr)
        if part and part.strip()
    )
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    summary = lines[-1] if lines else "sin resumen disponible"

    if proc.returncode == 0:
        return f"Pruebas completadas correctamente. {summary}."
    return f"Las pruebas fallaron. {summary}."


def _direct_explicit_git_commit(command: str) -> str | None:
    match = re.search(
        r"(?is)\b(?:haz|hacer|crea|crear)?\s*(?:un\s+)?commit(?:\s+git)?"
        r"(?:\s+de\s+los\s+cambios\s+versionados)?\s+"
        r"con\s+(?:el\s+)?mensaje\s+(.+)$",
        command.strip(),
    )
    if match is None:
        return None

    message = " ".join(match.group(1).strip().strip("\"'").split())
    message = re.sub(
        r"(?is)\s+y\s+no\s+(?:incluyas|agregues)\s+"
        r"(?:archivos\s+)?no\s+rastre(?:ados|es)\s*$",
        "",
        message,
    ).strip()

    if not message:
        return "Necesito un mensaje explicito para crear el commit."
    if len(message) > 200:
        return "El mensaje del commit es demasiado largo; usa hasta 200 caracteres."

    repo = _repo_root().resolve()
    common = {
        "cwd": repo,
        "capture_output": True,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
        "timeout": 20,
        "check": False,
        "creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0),
    }

    staged = subprocess.run(
        ["git", "diff", "--cached", "--name-only"],
        **common,
    )
    if staged.returncode != 0:
        return "No pude verificar el area staged de Git."
    if staged.stdout.strip():
        return (
            "Hay cambios staged previos. No cree el commit para evitar "
            "mezclar cambios existentes."
        )

    changed = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=ACDMRTUXB"],
        **common,
    )
    if changed.returncode != 0:
        return "No pude identificar los cambios versionados de Git."

    paths = [line.strip() for line in changed.stdout.splitlines() if line.strip()]
    if not paths:
        return "No hay cambios versionados pendientes para crear un commit."

    add = subprocess.run(
        ["git", "add", "-u", "--", *paths],
        **common,
    )
    if add.returncode != 0:
        return "No pude preparar los cambios versionados para el commit."

    commit = subprocess.run(
        ["git", "commit", "-m", message],
        **common,
    )
    if commit.returncode != 0:
        subprocess.run(
            ["git", "restore", "--staged", "--", *paths],
            **common,
        )
        return "No pude crear el commit; restaure el area staged."

    head = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        **common,
    )
    sha = head.stdout.strip() if head.returncode == 0 else ""
    suffix = f" Commit {sha}." if sha else ""
    noun = "archivo versionado" if len(paths) == 1 else "archivos versionados"
    return (
        f"Commit creado con {len(paths)} {noun}. "
        f"No agregue archivos no rastreados.{suffix}"
    )


def _direct_explicit_git_branch(command: str) -> str | None:
    match = re.search(
        r"(?is)\b(?:crea|crear|nueva)\s+(?:una\s+)?rama\s+"
        r"([a-z0-9][a-z0-9._/-]*)"
        r"(?:\s+desde\s+(?:la\s+rama\s+)?(?:main|master))?\s*$",
        normalize(command),
    )
    if match is None:
        return None

    branch = match.group(1).strip()
    allowed_prefixes = (
        "feature/",
        "fix/",
        "perf/",
        "refactor/",
        "chore/",
        "docs/",
        "test/",
    )
    if not branch.startswith(allowed_prefixes):
        return (
            "La rama debe usar un prefijo permitido: feature, fix, perf, "
            "refactor, chore, docs o test."
        )

    repo = _repo_root().resolve()
    common = {
        "cwd": repo,
        "capture_output": True,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
        "timeout": 20,
        "check": False,
        "creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0),
    }

    current_proc = subprocess.run(
        ["git", "branch", "--show-current"],
        **common,
    )
    current = (
        current_proc.stdout.strip()
        if current_proc.returncode == 0
        else ""
    )
    if current.lower() not in {"main", "master"}:
        return (
            "Solo creo ramas nuevas desde main o master. "
            f"La rama actual es {current or 'desconocida'}."
        )

    dirty = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=no"],
        **common,
    )
    if dirty.returncode != 0:
        return "No pude verificar el estado de Git antes de crear la rama."
    if dirty.stdout.strip():
        return (
            "Hay cambios versionados pendientes. No cree la rama para evitar "
            "mezclar trabajo sin commit."
        )

    valid = subprocess.run(
        ["git", "check-ref-format", "--branch", branch],
        **common,
    )
    if valid.returncode != 0:
        return "El nombre solicitado no es una rama Git valida."

    exists = subprocess.run(
        ["git", "show-ref", "--verify", "--quiet", f"refs/heads/{branch}"],
        **common,
    )
    if exists.returncode == 0:
        return f"La rama {branch} ya existe localmente."
    if exists.returncode not in {0, 1}:
        return "No pude verificar si la rama ya existe."

    create = subprocess.run(
        ["git", "switch", "-c", branch],
        **common,
    )
    if create.returncode != 0:
        return f"No pude crear la rama {branch}."

    verify = subprocess.run(
        ["git", "branch", "--show-current"],
        **common,
    )
    created = verify.stdout.strip() if verify.returncode == 0 else ""
    if created != branch:
        return (
            f"Git intento crear {branch}, pero no pude verificar la rama activa."
        )

    return f"Rama creada y verificada: {branch}."


def _direct_explicit_main_sync(command: str) -> str | None:
    n = normalize(command)
    if not any(
        phrase in n
        for phrase in (
            "vuelve a main y actualiza",
            "volver a main y actualizar",
            "regresa a main y actualiza",
            "regresar a main y actualizar",
            "cambia a main y actualiza",
        )
    ):
        return None

    repo = _repo_root().resolve()
    common = {
        "cwd": repo,
        "capture_output": True,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
        "timeout": 30,
        "check": False,
        "creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0),
    }

    dirty = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=no"],
        **common,
    )
    if dirty.returncode != 0:
        return "No pude verificar el estado de Git antes de volver a main."
    if dirty.stdout.strip():
        return (
            "Hay cambios versionados pendientes. No cambie de rama para evitar "
            "perder contexto de trabajo."
        )

    branch_check = subprocess.run(
        ["git", "show-ref", "--verify", "--quiet", "refs/heads/main"],
        **common,
    )
    target = "main"
    if branch_check.returncode == 1:
        master_check = subprocess.run(
            ["git", "show-ref", "--verify", "--quiet", "refs/heads/master"],
            **common,
        )
        if master_check.returncode == 0:
            target = "master"
        else:
            return "No encuentro una rama local main o master."
    elif branch_check.returncode != 0:
        return "No pude verificar la rama principal local."

    switch = subprocess.run(
        ["git", "switch", target],
        **common,
    )
    if switch.returncode != 0:
        return f"No pude cambiar a la rama {target}."

    remote = subprocess.run(
        ["git", "remote", "get-url", "origin"],
        **common,
    )
    if remote.returncode != 0 or not remote.stdout.strip():
        return f"Volvi a {target}, pero no encuentro el remoto origin para actualizar."

    fetch = subprocess.run(
        ["git", "fetch", "origin", target],
        **common,
    )
    if fetch.returncode != 0:
        return f"Volvi a {target}, pero no pude actualizar desde origin."

    merge = subprocess.run(
        ["git", "merge", "--ff-only", f"origin/{target}"],
        **common,
    )
    if merge.returncode != 0:
        return (
            f"Volvi a {target}, pero la actualizacion no fue fast-forward. "
            "No hice merge automatico."
        )

    verify = subprocess.run(
        ["git", "branch", "--show-current"],
        **common,
    )
    current = verify.stdout.strip() if verify.returncode == 0 else ""
    if current != target:
        return f"No pude verificar que la rama activa sea {target}."

    head = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        **common,
    )
    sha = head.stdout.strip() if head.returncode == 0 else ""
    suffix = f" HEAD {sha}." if sha else ""
    return f"Rama {target} activa y actualizada por fast-forward.{suffix}"


def _direct_explicit_git_push(command: str) -> str | None:
    n = normalize(command)
    if not any(
        phrase in n
        for phrase in (
            "haz push de la rama actual",
            "hacer push de la rama actual",
            "haz push al remoto origin",
            "hacer push al remoto origin",
            "push de la rama actual",
        )
    ):
        return None

    repo = _repo_root().resolve()
    common = {
        "cwd": repo,
        "capture_output": True,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
        "timeout": 30,
        "check": False,
        "creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0),
    }

    branch_proc = subprocess.run(
        ["git", "branch", "--show-current"],
        **common,
    )
    branch = branch_proc.stdout.strip() if branch_proc.returncode == 0 else ""
    if not branch:
        return "No puedo hacer push porque Git no esta en una rama."
    if branch.lower() in {"main", "master"}:
        return f"No hago push directo desde la rama protegida {branch}."

    dirty = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=no"],
        **common,
    )
    if dirty.returncode != 0:
        return "No pude verificar el estado de Git antes del push."
    if dirty.stdout.strip():
        return (
            "Hay cambios versionados sin commit. No hice push para evitar "
            "publicar una rama incompleta."
        )

    remote = subprocess.run(
        ["git", "remote", "get-url", "origin"],
        **common,
    )
    if remote.returncode != 0 or not remote.stdout.strip():
        return "No encuentro el remoto origin; no hice push."

    push = subprocess.run(
        ["git", "push", "-u", "origin", branch],
        **common,
    )
    if push.returncode != 0:
        detail = (push.stderr or push.stdout).strip().splitlines()
        reason = detail[-1] if detail else "Git rechazo el push."
        return f"No pude hacer push de {branch}. {reason}"

    return f"Push completado y verificado para la rama {branch} en origin."


def direct(command: str) -> str | None:
    n = normalize(command)
    pytest_answer = _direct_explicit_pytest(command)
    if pytest_answer is not None:
        return pytest_answer
    commit_answer = _direct_explicit_git_commit(command)
    if commit_answer is not None:
        return commit_answer
    branch_answer = _direct_explicit_git_branch(command)
    if branch_answer is not None:
        return branch_answer
    main_sync_answer = _direct_explicit_main_sync(command)
    if main_sync_answer is not None:
        return main_sync_answer
    push_answer = _direct_explicit_git_push(command)
    if push_answer is not None:
        return push_answer
    write_answer = _direct_explicit_file_write(command)
    if write_answer is not None:
        return write_answer
    edit_answer = _direct_explicit_file_edit(command)
    if edit_answer is not None:
        return edit_answer
    delete_answer = _direct_explicit_file_delete(command)
    if delete_answer is not None:
        return delete_answer
    app_answer = _open_windows_app(command)
    if app_answer is not None:
        return app_answer
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

    if any(
        phrase in n
        for phrase in (
            "verifica el directorio actual",
            "verificar el directorio actual",
            "directorio actual",
            "ruta actual del proyecto",
        )
    ):
        repo = _repo_root()
        proc = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=repo,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        path = proc.stdout.strip()
        return (
            f"Directorio actual verificado: {path}."
            if proc.returncode == 0 and path
            else f"Directorio actual: {repo}."
        )

    if any(
        phrase in n
        for phrase in (
            "revisa el estado del repositorio",
            "revisar el estado del repositorio",
            "identifica archivos modificados",
            "resume si hay algo pendiente",
        )
    ):
        repo = _repo_root()
        proc = subprocess.run(
            ["git", "status", "--short"],
            cwd=repo,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if proc.returncode != 0:
            return "No pude revisar el repositorio."
        changes = [line for line in proc.stdout.splitlines() if line.strip()]
        if not changes:
            return (
                "Repositorio revisado sin modificar archivos. "
                "No hay cambios pendientes."
            )

        tracked = [line for line in changes if not line.startswith("??")]
        untracked = [line for line in changes if line.startswith("??")]
        pending_names = [
            line[3:].strip() if len(line) > 3 else line.strip()
            for line in changes
        ]
        preview = ", ".join(pending_names[:6])
        suffix = "" if len(pending_names) <= 6 else f", y {len(pending_names) - 6} mas"

        parts: list[str] = []
        if tracked:
            noun = "archivo versionado modificado" if len(tracked) == 1 else "archivos versionados modificados"
            parts.append(f"{len(tracked)} {noun}")
        if untracked:
            noun = "archivo no rastreado" if len(untracked) == 1 else "archivos no rastreados"
            parts.append(f"{len(untracked)} {noun}")

        return (
            "Repositorio revisado sin modificar archivos. Hay "
            + " y ".join(parts)
            + f". Pendientes: {preview}{suffix}."
        )

    if any(
        phrase in n
        for phrase in (
            "resume los cambios git",
            "resumir los cambios git",
            "revisa el diff",
            "revisar el diff",
            "git diff",
            "que cambio en git",
        )
    ):
        repo = _repo_root()
        proc = subprocess.run(
            ["git", "diff", "--name-status", "HEAD"],
            cwd=repo,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if proc.returncode != 0:
            return "No pude revisar el diff de Git."
        lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
        if not lines:
            return "No hay diferencias versionadas pendientes en Git."

        changes: list[str] = []
        for line in lines[:8]:
            parts = line.split("\t", 1)
            status = parts[0].strip()
            path = parts[1].strip() if len(parts) > 1 else ""
            label = {
                "M": "modificado",
                "A": "agregado",
                "D": "eliminado",
                "R": "renombrado",
            }.get(status[:1], status)
            changes.append(f"{path} ({label})" if path else label)

        suffix = "" if len(lines) <= 8 else f", y {len(lines) - 8} mas"
        return (
            f"Git tiene diferencias en {len(lines)} archivos versionados: "
            + ", ".join(changes)
            + suffix
            + "."
        )

    if "estado git" in n or "git status" in n:
        repo = _repo_root()
        proc = subprocess.run(
            ["git", "status", "--short"],
            cwd=repo,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if proc.returncode != 0:
            return "No pude consultar el estado de Git."
        changes = [line for line in proc.stdout.splitlines() if line.strip()]
        if not changes:
            return "Git esta limpio. No hay cambios locales."
        untracked = [line for line in changes if line.startswith("??")]
        tracked = [line for line in changes if not line.startswith("??")]
        if tracked and untracked:
            return (
                f"Git tiene {len(tracked)} cambios versionados y "
                f"{len(untracked)} archivos no rastreados."
            )
        if tracked:
            return f"Git tiene {len(tracked)} cambios versionados."
        return f"Git tiene {len(untracked)} archivos no rastreados."

    if any(
        phrase in n
        for phrase in (
            "lista archivos del proyecto",
            "lista los archivos del proyecto",
            "lista el contenido del directorio del proyecto",
            "listar el contenido del directorio del proyecto",
            "lista el contenido del directorio",
            "listar el contenido del directorio",
        )
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
    if any(
        phrase in n
        for phrase in (
            "que puedes hacer",
            "que sabes hacer",
            "ayuda de voz",
            "comandos de voz",
        )
    ):
        return (
            "Puedo abrir el panel, chat, agentes, Visual Studio Code, Explorador, "
            "PowerShell, Docker Desktop y Chrome; consultar Git, archivos, Docker "
            "y el estado del sistema; y enviar preguntas libres al operador Jarvis."
        )
    if "ultimo commit" in n or "ultimo cambio git" in n or "git log" in n:
        repo = _repo_root()
        proc = subprocess.run(
            ["git", "log", "-1", "--oneline"],
            cwd=repo,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        line = proc.stdout.strip()
        return (
            f"Ultimo commit: {line}."
            if proc.returncode == 0 and line
            else "No pude consultar el ultimo commit."
        )
    if "estado docker" in n or "docker status" in n:
        proc = subprocess.run(
            ["docker", "version", "--format", "{{.Server.Version}}"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        version = proc.stdout.strip()
        return (
            f"Docker esta operativo. Version del servidor {version}."
            if proc.returncode == 0 and version
            else "Docker no esta respondiendo."
        )
    if "estado autonomo" in n or "estado de autonomia" in n:
        agent_id = _agent_id_by_name(AUTONOMY_AGENT_NAME)
        if not agent_id:
            return "No hay un operador autonomo creado."
        agent = api(f"/v1/managed-agents/{agent_id}", timeout=10)
        status = str(agent.get("status") or "desconocido")
        activity = str(agent.get("current_activity") or "").strip()
        summary = str(agent.get("summary_memory") or "").strip()
        detail = activity or summary[:180]
        return f"El operador autonomo esta {status}. {detail}".strip()
    if (
        "deten trabajo autonomo" in n
        or "detener trabajo autonomo" in n
        or "pausa trabajo autonomo" in n
    ):
        agent_id = _agent_id_by_name(AUTONOMY_AGENT_NAME)
        if not agent_id:
            return "No hay un operador autonomo creado."
        api(f"/v1/managed-agents/{agent_id}/pause", {}, timeout=10)
        return "Trabajo autonomo pausado."
    if "reanuda trabajo autonomo" in n or "reanudar trabajo autonomo" in n:
        agent_id = _agent_id_by_name(AUTONOMY_AGENT_NAME)
        if not agent_id:
            return "No hay un operador autonomo creado."
        api(f"/v1/managed-agents/{agent_id}/resume", {}, timeout=10)
        return "Trabajo autonomo reanudado."

    if "lista contenedores" in n or "listar contenedores" in n or "docker ps" in n:
        proc = subprocess.run(
            ["docker", "ps", "--format", "{{.Names}}"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        names = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
        if proc.returncode != 0:
            return "No pude consultar los contenedores de Docker."
        if not names:
            return "No hay contenedores Docker en ejecucion."
        preview = ", ".join(names[:6])
        suffix = "" if len(names) <= 6 else f", y {len(names) - 6} mas"
        return f"Contenedores en ejecucion: {preview}{suffix}."
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
                    "Eres Jarvis. Responde en espanol, breve y orientado a ejecucion."
                ),
            },
            {"role": "user", "content": command},
        ],
        "options": {"temperature": 0.2, "num_predict": 120, "num_ctx": 2048},
        "keep_alive": "30m",
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


def _agent_id_by_name(name: str) -> str | None:
    try:
        payload = api("/v1/managed-agents", timeout=10)
    except Exception:
        return None
    for agent in payload.get("agents", []):
        if str(agent.get("status") or "").strip().casefold() == "archived":
            continue
        if str(agent.get("name", "")).strip() == name:
            return str(agent.get("id") or "") or None
    return None


def _voice_agent_id() -> str | None:
    agent_id = _agent_id_by_name(VOICE_AGENT_NAME)
    if agent_id:
        return agent_id
    try:
        payload = api("/v1/managed-agents", timeout=10)
    except Exception:
        return None
    for agent in payload.get("agents", []):
        if (
            str(agent.get("name", ""))
            .strip()
            .casefold()
            .startswith("jarvis voice operator")
        ):
            return str(agent.get("id") or "") or None
    return None


def _runtime_device_id() -> str:
    voice_id = _voice_agent_id()
    if not voice_id:
        return ""
    try:
        agent = api(f"/v1/managed-agents/{voice_id}", timeout=10)
    except Exception:
        return ""
    return str((agent.get("config") or {}).get("runtime_device_id") or "").strip()


def _autonomy_config() -> dict[str, Any]:
    runtime_device_id = _runtime_device_id()
    workspace = str(_repo_root())
    instruction = (
        "Autonomous executor. Execute the latest user objective with REAL tools. "
        "You DO have execution tools. Only the tool schemas provided by the runtime "
        "for the current objective are available. Never invent or call a tool that is not "
        "explicitly listed for this objective. TOOL FIRST: for filesystem, process, test, Git, or system "
        "actions, call one of those tools before any prose. Never say that you cannot "
        "access the filesystem or execute commands when these tools are available. "
        "For write_file, path MUST be the exact absolute target FILE path from the "
        "objective; never pass the workspace directory itself as the path. Missing parent "
        "directories are recovered automatically by the runtime; do not create a directory "
        "using the target file path. "
        "Never claim execution without a successful tool result. The exact Windows workspace is "
        f"{workspace}. Use only real absolute paths in that workspace. "
        "For long work iterate change -> test -> verify -> commit/push when requested. "
        "Retry recoverable failures. Ask only for missing credentials, irreversible "
        "risk, or a decision that cannot be inferred. Output AUTONOMY_DONE only "
        "after every requested action has real evidence."
    )
    return {
        "model": AUTONOMY_MODEL,
        "instruction": instruction,
        "system_prompt": instruction,
        "schedule_type": "interval",
        "schedule_value": 45,
        "timezone": "America/Guayaquil",
        "auto_pause_on_done": True,
        "completion_marker": "AUTONOMY_DONE",
        "completion_requires_tool_evidence": True,
        "compact_prompt": True,
        "temperature": 0.1,
        "max_turns": 12,
        "max_output_tokens": 256,
        "num_ctx": 4096,
        "timeout_seconds": 300,
        "max_stall_retries": 2,
        "workspace": workspace,
        "runtime_machine": "trabajo",
        "runtime_machine_candidates": ["trabajo", "MarketingIndo"],
        "runtime_device_id": runtime_device_id,
        "runtime_machine_status": "online" if runtime_device_id else "unknown",
        "mcp_tools": True,
        "mcp_tool_allowlist": [
            "start_process",
            "read_process_output",
            "read_file",
            "write_file",
            "edit_block",
            "list_directory",
            "list_processes",
            "kill_process",
        ],
        "tools": [],
    }


def _autonomy_agent_id(config: dict[str, Any] | None = None) -> str:
    config = config or _autonomy_config()
    existing = _agent_id_by_name(AUTONOMY_AGENT_NAME)
    if existing:
        api(
            f"/v1/managed-agents/{existing}",
            {
                "agent_type": "operative",
                "config": config,
                "summary_memory": "",
            },
            timeout=20,
            method="PATCH",
        )
        return existing

    created = api(
        "/v1/managed-agents",
        {
            "name": AUTONOMY_AGENT_NAME,
            "agent_type": "operative",
            "config": config,
        },
        timeout=20,
    )
    agent_id = str(created.get("id") or "")
    if not agent_id:
        raise RuntimeError("No se pudo crear el operador autonomo.")
    return agent_id


_AUTONOMY_REPO_PREFIXES = (
    "assets",
    "configs",
    "deploy",
    "desktop",
    "docs",
    "examples",
    "frontend",
    "rust",
    "scripts",
    "src",
    "tests",
)


def _ground_autonomous_command(command: str) -> str:
    """Expand known repo-relative paths and foreground the exact Windows workspace."""
    workspace = str(_repo_root())
    prefixes = "|".join(re.escape(item) for item in _AUTONOMY_REPO_PREFIXES)
    pattern = re.compile(
        rf"(?<![A-Za-z0-9_:\\/])((?:{prefixes})[\\/][A-Za-z0-9_.\\/\-]+)"
    )

    def replace(match: re.Match[str]) -> str:
        relative = match.group(1).replace("\\", os.sep).replace("/", os.sep)
        return str(Path(workspace) / relative)

    grounded = pattern.sub(replace, command)
    return (
        f"EXACT WINDOWS WORKSPACE: {workspace}. "
        "Use exact absolute Windows paths from this instruction and never use "
        "placeholder paths. "
        + grounded
    )


def _autonomy_tool_allowlist(command: str) -> list[str]:
    """Advertise only the MCP tools needed for one autonomous objective."""
    n = normalize(command)
    selected: list[str] = []

    def add(*names: str) -> None:
        for name in names:
            if name not in selected:
                selected.append(name)

    if (
        "list_directory" in n
        or "lista el contenido" in n
        or "listar el contenido" in n
        or "lista directorio" in n
        or "listar directorio" in n
    ):
        add("list_directory")

    if any(
        term in n
        for term in (
            "crea ",
            "crear ",
            "escribe ",
            "escribir ",
            "write_file",
            "nuevo archivo",
        )
    ):
        add("write_file")

    if any(
        term in n
        for term in (
            "modifica ",
            "modificar ",
            "edita ",
            "editar ",
            "ajusta ",
            "ajustar ",
            "edit_block",
        )
    ):
        add("read_file", "edit_block")

    if any(
        term in n
        for term in (
            "lee ",
            "leer ",
            "read_file",
            "revisa el archivo",
            "contenido del archivo",
        )
    ):
        add("read_file")

    if any(
        term in n
        for term in (
            "ejecuta ",
            "ejecutar ",
            "git ",
            "pytest",
            "test ",
            "tests",
            "prueba",
            "commit",
            "push",
            "docker",
            "terminal",
            "comando",
            "start_process",
        )
    ):
        add("start_process", "read_process_output")

    if any(
        term in n
        for term in (
            "lista procesos",
            "listar procesos",
            "list_processes",
            "mata proceso",
            "deten proceso",
            "kill_process",
        )
    ):
        add("list_processes", "kill_process")

    if not selected:
        add("start_process", "read_process_output", "read_file", "list_directory")

    return selected



_AUTONOMY_COMPACT_TOOL_SPECS: dict[str, dict[str, Any]] = {
    "create_directory": {
        "type": "function",
        "function": {
            "name": "create_directory",
            "description": "Create a Windows directory using an absolute path.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                },
                "required": ["path"],
                "additionalProperties": False,
            },
        },
    },
    "list_directory": {
        "type": "function",
        "function": {
            "name": "list_directory",
            "description": "List a Windows directory using an absolute path.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "depth": {"type": "number"},
                },
                "required": ["path"],
                "additionalProperties": False,
            },
        },
    },
    "write_file": {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write text to a file using an absolute Windows path.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                    "mode": {
                        "type": "string",
                        "enum": ["rewrite", "append"],
                    },
                },
                "required": ["path", "content"],
                "additionalProperties": False,
            },
        },
    },
    "start_process": {
        "type": "function",
        "function": {
            "name": "start_process",
            "description": "Run a Windows command or PowerShell command.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string"},
                    "timeout_ms": {"type": "number"},
                    "shell": {"type": "string"},
                },
                "required": ["command", "timeout_ms"],
                "additionalProperties": False,
            },
        },
    },
    "read_process_output": {
        "type": "function",
        "function": {
            "name": "read_process_output",
            "description": "Read output from a process started by start_process.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pid": {"type": "number"},
                    "timeout_ms": {"type": "number"},
                    "offset": {"type": "number"},
                    "length": {"type": "number"},
                },
                "required": ["pid"],
                "additionalProperties": False,
            },
        },
    },
}


def _autonomy_tool_specs(names: list[str]) -> list[dict[str, Any]]:
    """Return compact advertised specs while retaining real MCP backends."""
    return [
        json.loads(json.dumps(_AUTONOMY_COMPACT_TOOL_SPECS[name]))
        for name in names
        if name in _AUTONOMY_COMPACT_TOOL_SPECS
    ]


def _autonomy_completion_requirements(command: str) -> list[str]:
    n = normalize(command)
    requirements: list[str] = []

    if any(term in n for term in ("crea ", "crear ", "modifica ", "modificar ", "edita ", "editar ", "escribe ", "escribir ", "implementa ", "implementar ")):
        requirements.append("write")
    if any(term in n for term in ("pytest", "prueba", "pruebas", "test ", "tests/")):
        requirements.append("pytest")
    if "start_process" in n:
        requirements.append("process_start")
    if "autonomy_gate_ok" in n or "autonomy gate ok" in n:
        requirements.append("autonomy_gate_ok")
    if "git status" in n:
        requirements.append("git_status")
    if "git diff" in n:
        requirements.append("git_diff")
    if "commit" in n:
        requirements.append("git_commit")
    if "push" in n:
        requirements.append("git_push")
    if "exit code 0" in n or "codigo de salida 0" in n:
        requirements.append("process_exit_0")

    return requirements


def _prepare_autonomy_models() -> None:
    """Free CPU/RAM from non-autonomy LLMs before a durable objective starts."""
    protected_models = {AUTONOMY_MODEL, MODEL}
    other_models = {
        "jarvis-voice:latest",
        "llama3.2:1b",
        "granite-code:3b",
    } - protected_models
    for model in sorted(other_models):
        if not model:
            continue
        try:
            subprocess.run(
                ["ollama", "stop", model],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=10,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            log.warning("Could not unload Ollama model %s: %s", model, exc)


def _wait_for_autonomy_idle(agent_id: str, timeout_seconds: float = 20.0) -> None:
    """Wait for a previous autonomous tick to finish before replacing its objective."""
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        agent = api(f"/v1/managed-agents/{agent_id}", timeout=10)
        status = str(agent.get("status") or "idle")
        if status != "running":
            return

        try:
            runtime = api(
                f"/v1/managed-agents/{agent_id}/runtime",
                timeout=5,
            )
        except Exception:
            runtime = {}

        if runtime.get("worker_alive") is False:
            api(
                f"/v1/managed-agents/{agent_id}/recover",
                {},
                timeout=10,
            )
            return

        time.sleep(0.5)
    raise TimeoutError(
        "El trabajo autonomo anterior sigue ejecutandose; no se reemplazo el objetivo."
    )


def _wait_for_verified_autonomy_reply(
    agent_id: str,
    sent_at: float,
    tool_name: str,
    timeout_seconds: float = 6.0,
) -> str | None:
    """Return a post-objective reply only after verified tool evidence appears."""
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        messages = api(
            f"/v1/managed-agents/{agent_id}/messages",
            timeout=10,
        ).get("messages", [])
        candidates = sorted(
            (
                message
                for message in messages
                if message.get("direction") == "agent_to_user"
                and float(message.get("created_at") or 0.0) >= sent_at
            ),
            key=lambda message: float(message.get("created_at") or 0.0),
            reverse=True,
        )
        for message in candidates:
            tool_calls = message.get("tool_calls") or []
            for call in tool_calls:
                if not isinstance(call, dict):
                    continue
                if str(call.get("tool") or call.get("name") or "") != tool_name:
                    continue
                if call.get("success") is not True:
                    continue
                result = str(call.get("result") or "").strip()
                if result:
                    return result
                content = str(message.get("content") or "").strip()
                if content:
                    return content

        agent = api(f"/v1/managed-agents/{agent_id}", timeout=10)
        if str(agent.get("status") or "") in {
            "error",
            "needs_attention",
            "budget_exceeded",
        }:
            return None
        time.sleep(0.2)
    return None


def _summarize_list_directory_result(content: str) -> str:
    """Create a concise voice response from a verified directory listing."""
    lines = [line.strip() for line in str(content or "").splitlines()]
    directories = sum(line.startswith("[DIR]") for line in lines)
    files = sum(line.startswith("[FILE]") for line in lines)
    if directories or files:
        return (
            "Verifiqué el workspace. "
            f"Encontré {directories} carpetas y {files} archivos."
        )
    return "Verifiqué el workspace correctamente."


def autonomous(command: str) -> str:
    """Queue a durable objective and let the scheduled worker continue it."""
    if not _ensure_api_available():
        return (
            "No pude recuperar el backend local de Jarvis. "
            "La tarea autonoma no se inicio."
        )
    _prepare_autonomy_models()

    config = _autonomy_config()
    grounded_command = _ground_autonomous_command(command)
    tool_allowlist = _autonomy_tool_allowlist(command)
    tool_names = ", ".join(tool_allowlist)
    config["instruction"] += (
        f" Available tools for this objective: {tool_names}. "
        "Use only these exact tool names and their provided schemas."
    )
    config["system_prompt"] = config["instruction"]
    config["mcp_tool_allowlist"] = tool_allowlist
    config["tools"] = _autonomy_tool_specs(tool_allowlist)
    config["completion_evidence_requirements"] = _autonomy_completion_requirements(command)
    config["completion_evidence_observed"] = []
    config["completion_tool_evidence_seen"] = False
    config["completion_followup_count"] = 0
    config["max_completion_followups"] = 6
    config["active_objective"] = grounded_command
    config["objective_token"] = str(time.time_ns())

    existing_id = _agent_id_by_name(AUTONOMY_AGENT_NAME)
    if existing_id:
        _wait_for_autonomy_idle(existing_id, timeout_seconds=45.0)
    agent_id = _autonomy_agent_id(config)
    try:
        api("/v1/operations/machines/probe", {}, timeout=15)
    except Exception as exc:
        log.warning("Autonomous machine probe failed: %s", exc)
    agent = api(f"/v1/managed-agents/{agent_id}", timeout=10)
    status = str(agent.get("status") or "idle")

    if status == "paused":
        api(f"/v1/managed-agents/{agent_id}/resume", {}, timeout=10)
        status = "idle"
    elif status in {"error", "needs_attention", "budget_exceeded"}:
        api(f"/v1/managed-agents/{agent_id}/recover", {}, timeout=10)
        status = "idle"

    sent = api(
        f"/v1/managed-agents/{agent_id}/messages",
        {
            "content": (
                "NEW AUTONOMOUS OBJECTIVE. Replace any previous unfinished objective. "
                + grounded_command
            ),
            "mode": "queued",
            "stream": False,
        },
        timeout=15,
    )
    sent_at = float(sent.get("created_at") or time.time())
    if status != "running":
        api(f"/v1/managed-agents/{agent_id}/run", {}, timeout=15)

    if tool_allowlist == ["list_directory"]:
        verified = _wait_for_verified_autonomy_reply(
            agent_id,
            sent_at,
            "list_directory",
            timeout_seconds=6.0,
        )
        if verified:
            return _summarize_list_directory_result(verified)

    return (
        "Entendido. Inicie el trabajo autonomo. Continuare por etapas, "
        "validare cada cambio y me detendre automaticamente cuando termine."
    )


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
                    if _requires_tool_evidence(command) and not message.get(
                        "tool_calls"
                    ):
                        raise UnverifiedVoiceActionError(
                            "La respuesta no contiene evidencia real de herramienta."
                        )
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

    # Conversational questions do not need the managed-agent queue. Route
    # them directly to the already-local Ollama model to avoid polling delay.
    if not _requires_tool_evidence(command):
        return chat(command)
    if not _is_autonomous_objective(command):
        return (
            "Entendi una posible accion, pero la instruccion no es suficientemente "
            "clara para iniciar trabajo autonomo. Indica la tarea concreta."
        )

    try:
        return autonomous(command)
    except Exception as exc:
        log.warning("Autonomous voice execution failed: %s", exc)
        return (
            "No pude iniciar el trabajo autonomo de forma verificable. "
            "La orden no fue aplicada."
        )


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


def _wait_for_wake_on_device(
    detector,
    device: int | str | None,
) -> float | None:
    import numpy as np
    import sounddevice as sd

    detector.reset()
    last_state = 0.0
    last_detector_reset = time.monotonic()
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
            frame_rms = (
                float(np.sqrt(np.mean(frame.astype(np.float64) ** 2)))
                if len(frame)
                else 0.0
            )
            now = time.monotonic()
            if now - last_detector_reset >= 30.0:
                detector.reset()
                last_detector_reset = now
            if now - last_state >= 1.0:
                state(
                    "listening",
                    wake_word="Hey Jarvis",
                    wake_score=round(score, 4),
                    audio_device=device,
                    sample_rate=input_rate,
                )
                last_state = now
            short_wake = score >= SHORT_WAKE_THRESHOLD and frame_rms >= SHORT_WAKE_RMS
            if score >= WAKE_THRESHOLD or short_wake:
                log.info("Wake detected score=%.4f rms=%.1f", score, frame_rms)
                return score
    return None


def wait_for_wake(detector) -> float | None:
    """Listen for the wake word, failing over when an input device breaks."""
    last_error: Exception | None = None
    for device in audio_device_candidates():
        try:
            return _wait_for_wake_on_device(detector, device)
        except Exception as exc:
            last_error = exc
            log.warning("Wake input failed on device %r: %s", device, exc)
            detector.reset()
    if last_error is not None:
        raise last_error
    return None

def capture_command(backend) -> str:
    state("awake", wake_word="Hey Jarvis")
    speak("Te escucho.")
    audio = record_voice_audio(
        silence_threshold=THRESHOLD,
        silence_seconds=0.9,
        startup_silence_seconds=3.0,
        max_seconds=10.0,
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
    audio = record_voice_audio(
        silence_threshold=THRESHOLD,
        silence_seconds=0.7,
        startup_silence_seconds=1.5,
        max_seconds=6.0,
    )
    amplitude = wav_rms(audio)
    if amplitude < max(40.0, THRESHOLD * 0.60):
        log.debug(
            "Fallback ignored low-level audio rms=%.1f threshold=%s",
            amplitude,
            THRESHOLD,
        )
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
    if not acquire_single_instance():
        log.info("Voice control already running; duplicate launch ignored")
        return 0
    STOP_PATH.unlink(missing_ok=True)

    from openjarvis.core.config import load_config
    from openjarvis.speech._discovery import get_speech_backend

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
                try:
                    score = wait_for_wake(detector)
                except Exception as exc:
                    log.exception(
                        "Wake detector failed; switching to Whisper fallback "
                        "for this session"
                    )
                    detector = None
                    wake_mode = "whisper-fallback"
                    state(
                        "recovering",
                        error=str(exc),
                        wake_mode=wake_mode,
                        recovery="whisper-fallback",
                    )
                    continue
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
