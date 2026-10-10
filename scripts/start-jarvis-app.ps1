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
        & $python -m openjarvis.cli stop *> $null
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
            'qwen3.5:4b',
            '--agent',
            'orchestrator'
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

$deadline = (Get-Date).AddSeconds(45)
while (
    (Get-Date) -lt $deadline -and
    (
        -not (Test-Url 'http://127.0.0.1:8000/health') -or
        -not (Test-Url 'http://127.0.0.1:5173/dashboard')
    )
) {
    Start-Sleep -Milliseconds 500
}

$voice = Join-Path $repo 'scripts\start-jarvis-voice.ps1'
if (Test-Path $voice) {
    Start-Process -FilePath 'powershell.exe' -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-File',$voice -WorkingDirectory $repo -WindowStyle Hidden
}

$programFilesX86 = [Environment]::GetFolderPath('ProgramFilesX86')
$programFiles = [Environment]::GetFolderPath('ProgramFiles')
$edge = @(
    (Join-Path $programFilesX86 'Microsoft\Edge\Application\msedge.exe'),
    (Join-Path $programFiles 'Microsoft\Edge\Application\msedge.exe')
) | Where-Object { Test-Path $_ } | Select-Object -First 1

if ($edge) {
    $edgeProfile = Join-Path $env:USERPROFILE '.openjarvis\edge-app-profile'
    New-Item -ItemType Directory -Force -Path $edgeProfile | Out-Null
    Start-Process -FilePath $edge -ArgumentList @(
        ('--user-data-dir=' + $edgeProfile),
        '--app=http://127.0.0.1:5173/dashboard',
        '--start-maximized',
        '--no-first-run'
    )
} else {
    Start-Process 'http://127.0.0.1:5173/dashboard'
}
