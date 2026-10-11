$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$python = Join-Path $repo '.venv\Scripts\pythonw.exe'

if (-not (Test-Path $python)) {
    throw "OpenJarvis virtual environment not found: $python"
}

$env:OPENJARVIS_WAKE_MODE = 'whisper-fallback'
$env:OPENJARVIS_AUDIO_DEVICE = 'default'
$env:OPENJARVIS_VOICE_THRESHOLD = '100'
$env:OPENJARVIS_WAKE_THRESHOLD = '0.05'
$env:OPENJARVIS_VOICE_MODEL = 'jarvis-voice'
$env:OPENJARVIS_SPEECH_HOTWORDS = 'Jarvis'
$env:OPENJARVIS_VOICE_REPO = $repo

$listenerPattern = 'openjarvis\.speech\.voice_control'
$listenerRunning = $false

try {
    $listenerRunning = @(
        Get-CimInstance Win32_Process -ErrorAction Stop |
            Where-Object {
                $_.Name -match '^pythonw?\.exe
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
 -and
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
