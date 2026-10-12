param(
    [string]$ComposeDir = $PSScriptRoot,
    [string]$N8nVersion = '2.35.5',
    [string]$NodeRuntimeDir = "$env:USERPROFILE\.openjarvis\n8n-runtime",
    [string]$NodeUserDir = "$env:USERPROFILE\.openjarvis\n8n-data"
)

$ErrorActionPreference = 'Stop'

function Test-N8nReady {
    try {
        $response = Invoke-WebRequest -Uri 'http://127.0.0.1:5678/healthz' -UseBasicParsing -TimeoutSec 3
        return ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500)
    } catch {
        return $false
    }
}

function Wait-N8nReady {
    param([int]$TimeoutSeconds = 90)
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        if (Test-N8nReady) {
            Write-Host '[n8n] Ready at http://127.0.0.1:5678'
            return
        }
        Start-Sleep -Seconds 2
    } while ((Get-Date) -lt $deadline)
    throw 'n8n did not become reachable on port 5678.'
}

function Test-DockerReady {
    try {
        docker info *> $null
        return ($LASTEXITCODE -eq 0)
    } catch {
        return $false
    }
}

function Start-N8nWithDocker {
    Push-Location $ComposeDir
    try {
        if (-not (Test-Path '.env') -and (Test-Path '.env.example')) {
            Copy-Item '.env.example' '.env'
            Write-Host '[n8n] Created .env from .env.example'
        }
        docker compose up -d
        if ($LASTEXITCODE -ne 0) { throw 'docker compose up failed.' }
        Wait-N8nReady
        Write-Host '[n8n] Runtime mode=docker'
    } finally {
        Pop-Location
    }
}

function Ensure-NodeRuntime {
    $entry = Join-Path $NodeRuntimeDir 'node_modules\n8n\bin\n8n'
    if (Test-Path $entry) { return $entry }
    New-Item -ItemType Directory -Force -Path $NodeRuntimeDir | Out-Null
    $npmCommand = Get-Command npm.cmd -ErrorAction SilentlyContinue
    $npm = if ($npmCommand) { $npmCommand.Source } else { Join-Path $env:ProgramFiles 'nodejs\npm.cmd' }
    if (-not (Test-Path $npm)) { throw 'Node npm.cmd was not found.' }
    Write-Host ('[n8n] Installing local n8n ' + $N8nVersion)
    & $npm install --prefix $NodeRuntimeDir ('n8n@' + $N8nVersion) --omit=dev --legacy-peer-deps --no-audit --no-fund
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $entry)) { throw 'Local n8n installation failed.' }
    return $entry
}

function Start-N8nWithNode {
    $entry = Ensure-NodeRuntime
    $nodeCommand = Get-Command node.exe -ErrorAction SilentlyContinue
    $node = if ($nodeCommand) { $nodeCommand.Source } else { Join-Path $env:ProgramFiles 'nodejs\node.exe' }
    if (-not (Test-Path $node)) { throw 'Node executable was not found.' }
    New-Item -ItemType Directory -Force -Path $NodeUserDir | Out-Null
    $env:N8N_USER_FOLDER = $NodeUserDir
    $env:N8N_HOST = '127.0.0.1'
    $env:N8N_LISTEN_ADDRESS = '127.0.0.1'
    $env:N8N_PORT = '5678'
    $env:N8N_PROTOCOL = 'http'
    $env:N8N_WEBHOOK_URL = 'http://127.0.0.1:5678/'
    $env:OPENJARVIS_BASE_URL = 'http://127.0.0.1:8000'
    $env:N8N_BLOCK_ENV_ACCESS_IN_NODE = 'false'
    $env:N8N_DIAGNOSTICS_ENABLED = 'false'
    $env:N8N_PERSONALIZATION_ENABLED = 'false'
    $logDir = Join-Path $env:USERPROFILE '.openjarvis'
    New-Item -ItemType Directory -Force -Path $logDir | Out-Null
    $stdout = Join-Path $logDir 'n8n.stdout.log'
    $stderr = Join-Path $logDir 'n8n.stderr.log'
    Write-Host '[n8n] Starting local Node runtime'
    Start-Process -FilePath $node -ArgumentList @($entry, 'start') -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr
    Wait-N8nReady
    Write-Host '[n8n] Runtime mode=node'
}

if (Test-N8nReady) {
    Write-Host '[n8n] Already ready at http://127.0.0.1:5678'
    exit 0
}

if (Test-DockerReady) {
    try {
        Start-N8nWithDocker
        exit 0
    } catch {
        Write-Warning ('Docker n8n startup failed; falling back to Node: ' + $_.Exception.Message)
    }
}

Start-N8nWithNode
