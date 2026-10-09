$ErrorActionPreference = 'SilentlyContinue'
$repo = Split-Path -Parent $PSScriptRoot

function Test-Url([string]$Url) {
    try {
        $r = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 2
        return $r.StatusCode -ge 200 -and $r.StatusCode -lt 500
    } catch {
        return $false
    }
}

if (-not (Test-Url 'http://127.0.0.1:8000/health')) {
    $python = Join-Path $repo '.venv\Scripts\python.exe'
    if (Test-Path $python) {
        Start-Process -FilePath $python -ArgumentList @(
            '-m',
            'openjarvis.cli',
            'start',
            '--host',
            '127.0.0.1',
            '--port',
            '8000',
            '--engine',
            'ollama',
            '--model',
            'qwen3.5:4b'
        ) -WorkingDirectory $repo -WindowStyle Hidden
    }
}

$frontend = Join-Path $repo 'frontend'
if (-not (Test-Url 'http://127.0.0.1:5173/dashboard')) {
    $npm = 'C:\Program Files\nodejs\npm.cmd'
    if (Test-Path $npm) {
        Start-Process -FilePath 'cmd.exe' -ArgumentList '/c', ('"' + $npm + '" run dev -- --host 127.0.0.1 --port 5173 --strictPort') -WorkingDirectory $frontend -WindowStyle Hidden
    }
}

$voice = Join-Path $repo 'scripts\start-jarvis-voice.ps1'
if (Test-Path $voice) {
    Start-Process -FilePath 'powershell.exe' -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-File',$voice -WorkingDirectory $repo -WindowStyle Hidden
}

$deadline = (Get-Date).AddSeconds(20)
while ((Get-Date) -lt $deadline -and -not (Test-Url 'http://127.0.0.1:5173/dashboard')) {
    Start-Sleep -Milliseconds 500
}

$edge = @(
    "$env:ProgramFiles(x86)\Microsoft\Edge\Application\msedge.exe",
    "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1

if ($edge) {
    Start-Process -FilePath $edge -ArgumentList '--app=http://127.0.0.1:5173/dashboard','--start-maximized'
} else {
    Start-Process 'http://127.0.0.1:5173/dashboard'
}
