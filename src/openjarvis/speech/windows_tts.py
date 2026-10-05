"""Windows local TTS backend using System.Speech."""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path
from typing import List

from openjarvis.core.registry import TTSRegistry
from openjarvis.speech.tts import TTSBackend, TTSResult


@TTSRegistry.register("windows")
class WindowsTTSBackend(TTSBackend):
    backend_id = "windows"

    def health(self) -> bool:
        return os.name == "nt"

    def available_voices(self) -> List[str]:
        if os.name != "nt":
            return []
        script = (
            "Add-Type -AssemblyName System.Speech; "
            "$s=New-Object System.Speech.Synthesis.SpeechSynthesizer; "
            "$s.GetInstalledVoices() | ForEach-Object { $_.VoiceInfo.Name }"
        )
        proc = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return [line.strip() for line in proc.stdout.splitlines() if line.strip()]

    def synthesize(
        self,
        text: str,
        *,
        voice_id: str = "",
        speed: float = 1.0,
        output_format: str = "wav",
    ) -> TTSResult:
        if os.name != "nt":
            raise RuntimeError("Windows TTS is available only on Windows")
        fd, raw_path = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        path = Path(raw_path)
        safe_text = text.replace("'", "''")
        safe_path = str(path).replace("'", "''")
        rate = max(-10, min(10, round((speed - 1.0) * 5)))
        voice_clause = ""
        if voice_id:
            safe_voice = voice_id.replace("'", "''")
            voice_clause = f"try {{ $s.SelectVoice('{safe_voice}') }} catch {{ }}; "
        script = (
            "Add-Type -AssemblyName System.Speech; "
            "$s=New-Object System.Speech.Synthesis.SpeechSynthesizer; "
            f"{voice_clause}$s.Rate={rate}; "
            f"$s.SetOutputToWaveFile('{safe_path}'); "
            f"$s.Speak('{safe_text}'); $s.Dispose()"
        )
        try:
            proc = subprocess.run(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
                capture_output=True,
                text=True,
                timeout=90,
                check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if proc.returncode != 0 or not path.exists():
                raise RuntimeError(
                    proc.stderr.strip() or "Windows speech synthesis failed"
                )
            audio = path.read_bytes()
        finally:
            path.unlink(missing_ok=True)
        return TTSResult(
            audio=audio, format="wav", voice_id=voice_id, sample_rate=22050
        )
