$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$python = Join-Path $repo '.venv\Scripts\pythonw.exe'

if (-not (Test-Path $python)) {
    throw "OpenJarvis virtual environment not found: $python"
}

$env:OPENJARVIS_WAKE_MODE = 'whisper-fallback'
$env:OPENJARVIS_WAKE_THRESHOLD = '0.14'
$env:OPENJARVIS_VOICE_THRESHOLD = '450'
$env:OPENJARVIS_AUDIO_DEVICE = 'wasapi-default'
$env:OPENJARVIS_VOICE_AGENT = 'Jarvis Voice Operator V2'
$env:OPENJARVIS_SPEECH_HOTWORDS = 'Jarvis'
$env:OPENJARVIS_VOICE_REPO = $repo
$env:JARVIS_NUM_CTX = '2048'

$listenerPattern = 'openjarvis\.speech\.voice_control'
$listenerRunning = $false

try {
    $listenerRunning = @(
        Get-CimInstance Win32_Process -ErrorAction Stop |
            Where-Object {
                $_.Name -match '^pythonw?\.exe$' -and
                $_.CommandLine -match $listenerPattern
            }
    ).Count -gt 0
}
catch {
    Write-Verbose "Could not inspect existing voice listener processes: $($_.Exception.Message)"
}

if ($listenerRunning) {
    Write-Host 'OpenJarvis voice listener is already running.'
    exit 0
}

Start-Process -FilePath $python `
    -ArgumentList '-m openjarvis.speech.voice_control' `
    -WorkingDirectory $repo `
    -WindowStyle Hidden
