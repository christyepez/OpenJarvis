param(
    [string]$ComposeDir = $PSScriptRoot
)

$ErrorActionPreference = 'Stop'

Push-Location $ComposeDir
try {
    if (-not (Test-Path '.env') -and (Test-Path '.env.example')) {
        Copy-Item '.env.example' '.env'
        Write-Host '[n8n] Created .env from .env.example'
    }

    docker compose up -d

    $deadline = (Get-Date).AddSeconds(60)
    do {
        Start-Sleep -Seconds 2
        try {
            $response = Invoke-WebRequest -Uri 'http://127.0.0.1:5678/' -UseBasicParsing -TimeoutSec 3
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500) {
                Write-Host '[n8n] Ready at http://127.0.0.1:5678'
                exit 0
            }
        } catch {
            # Container may still be starting.
        }
    } while ((Get-Date) -lt $deadline)

    docker compose ps
    throw 'n8n did not become reachable on port 5678.'
}
finally {
    Pop-Location
}
