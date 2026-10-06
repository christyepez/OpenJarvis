$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$python = Join-Path $repo '.venv\Scripts\pythonw.exe'

if (-not (Test-Path $python)) {
    throw "OpenJarvis virtual environment not found: $python"
}

$env:OPENJARVIS_WAKE_MODE = 'whisper-fallback'
$env:OPENJARVIS_AUDIO_DEVICE = '15'
$env:OPENJARVIS_VOICE_THRESHOLD = '450'
$env:OPENJARVIS_VOICE_REPO = $repo

Start-Process -FilePath $python `
    -ArgumentList '-m openjarvis.speech.voice_control' `
    -WorkingDirectory $repo `
    -WindowStyle Hidden
