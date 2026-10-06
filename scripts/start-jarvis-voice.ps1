$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$python = Join-Path $repo '.venv\Scripts\pythonw.exe'

if (-not (Test-Path $python)) {
    throw "OpenJarvis virtual environment not found: $python"
}

$env:OPENJARVIS_WAKE_MODE = 'auto'
$env:OPENJARVIS_AUDIO_DEVICE = 'default'
$env:OPENJARVIS_VOICE_THRESHOLD = '100'
$env:OPENJARVIS_WAKE_THRESHOLD = '0.05'
$env:OPENJARVIS_VOICE_MODEL = 'jarvis-voice'
$env:OPENJARVIS_SPEECH_HOTWORDS = 'Jarvis'
$env:OPENJARVIS_VOICE_REPO = $repo

Start-Process -FilePath $python `
    -ArgumentList '-m openjarvis.speech.voice_control' `
    -WorkingDirectory $repo `
    -WindowStyle Hidden
