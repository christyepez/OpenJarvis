param(
    [string]$OpenJarvisBaseUrl = 'http://127.0.0.1:8000',
    [string]$N8nBaseUrl = 'http://127.0.0.1:5678',
    [string]$TaskWebhookUrl = 'http://127.0.0.1:5678/webhook/jarvis/task',
    [string]$ResultWebhookUrl = 'http://127.0.0.1:5678/webhook/jarvis/result',
    [string]$Workspace = 'C:\\Users\\chris\\source\\repos\\OpenJarvis',
    [string]$RuntimeDeviceId = '',
    [string]$ApiKey = '',
    [switch]$SkipServiceRestart,
    [switch]$SkipSmoke
)

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot

function Invoke-Step {
    param([string]$Name, [scriptblock]$Action)
    Write-Host ('[bootstrap] ' + $Name)
    & $Action
}

function Wait-JarvisHealth {
    param([int]$TimeoutSeconds = 90)
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        try {
            $headers = @{}
            if ($ApiKey) { $headers.Authorization = 'Bearer ' + $ApiKey }
            $health = Invoke-RestMethod -Method GET -Uri ($OpenJarvisBaseUrl + '/health') -Headers $headers -TimeoutSec 5
            if ($health.status -eq 'ok') { return }
        } catch {
        }
        Start-Sleep -Seconds 2
    } while ((Get-Date) -lt $deadline)
    throw 'OpenJarvis did not become healthy within the timeout.'
}

Invoke-Step 'Configure OpenJarvis n8n environment' {
    & (Join-Path $root 'configure-openjarvis.ps1') -WebhookUrl $TaskWebhookUrl -ResultWebhookUrl $ResultWebhookUrl
    if (-not $?) { throw 'OpenJarvis n8n environment configuration failed.' }
}

Invoke-Step 'Start n8n container' {
    & (Join-Path $root 'start-n8n.ps1')
    if (-not $?) { throw 'n8n startup failed.' }
}

Invoke-Step 'Import and publish Jarvis n8n workflow' {
    & (Join-Path $root 'install-workflow.ps1')
    if (-not $?) { throw 'n8n workflow installation failed.' }
}

if (-not $SkipServiceRestart) {
    Invoke-Step 'Restart OpenJarvis scheduled task when installed' {
        $task = Get-ScheduledTask -TaskName 'OpenJarvis' -ErrorAction SilentlyContinue
        if ($task) {
            Stop-ScheduledTask -TaskName 'OpenJarvis' -ErrorAction SilentlyContinue
            Start-Sleep -Seconds 1
            Start-ScheduledTask -TaskName 'OpenJarvis'
        } else {
            Write-Host '[bootstrap] OpenJarvis scheduled task not installed; leaving current runtime unchanged.'
        }
    }
}

Invoke-Step 'Wait for OpenJarvis health' { Wait-JarvisHealth }

Invoke-Step 'Validate Autonomy V2 readiness' {
    $headers = @{}
    if ($ApiKey) { $headers.Authorization = 'Bearer ' + $ApiKey }
    $status = Invoke-RestMethod -Method GET -Uri ($OpenJarvisBaseUrl + '/v1/autonomy/status') -Headers $headers -TimeoutSec 10
    $status | ConvertTo-Json -Depth 10
    if (-not $status.ready) {
        throw ('Autonomy V2 is not ready. Blockers: ' + ($status.blockers -join ', '))
    }
}

if (-not $SkipSmoke) {
    Invoke-Step 'Run Autonomy V2 smoke' {
        & (Join-Path $root 'smoke-autonomy.ps1') -OpenJarvisBaseUrl $OpenJarvisBaseUrl -N8nBaseUrl $N8nBaseUrl -Workspace $Workspace -RuntimeDeviceId $RuntimeDeviceId -ApiKey $ApiKey
        if (-not $?) { throw 'Autonomy V2 smoke failed.' }
    }
}

Write-Host '[bootstrap] AUTONOMY_V2_BOOTSTRAP=PASS'
