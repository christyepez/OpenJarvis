param(
    [string]$Container = 'openjarvis-n8n',
    [string]$WorkflowPath = '/workflows/jarvis-task-dispatcher.json',
    [string]$WorkflowName = 'Jarvis Task Dispatcher',
    [string]$NodeRuntimeDir = "$env:USERPROFILE\.openjarvis\n8n-runtime",
    [string]$NodeUserDir = "$env:USERPROFILE\.openjarvis\n8n-data"
)

$ErrorActionPreference = 'Stop'

function Resolve-WorkflowId {
    param([string]$RawJson)
    $items = $RawJson | ConvertFrom-Json
    if ($items -isnot [System.Collections.IEnumerable] -or $items -is [string]) {
        $items = @($items)
    }
    $workflow = @($items) | Where-Object { $_.name -eq $WorkflowName } | Select-Object -First 1
    if (-not $workflow -or -not $workflow.id) {
        throw "Imported workflow '$WorkflowName' was not found."
    }
    return [string]$workflow.id
}

function Wait-N8nReady {
    param([int]$TimeoutSeconds = 90)
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        Start-Sleep -Seconds 2
        try {
            $response = Invoke-WebRequest -Uri 'http://127.0.0.1:5678/healthz' -UseBasicParsing -TimeoutSec 3
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500) { return }
        } catch {
        }
    } while ((Get-Date) -lt $deadline)
    throw 'n8n did not become reachable after workflow publish.'
}

function Test-DockerContainer {
    try {
        $running = docker inspect -f '{{.State.Running}}' $Container 2>$null
        return ($LASTEXITCODE -eq 0 -and $running -eq 'true')
    } catch {
        return $false
    }
}

function Install-WorkflowDocker {
    $exportPath = '/tmp/openjarvis-workflows.json'
    Write-Host '[n8n] Importing Jarvis workflow via Docker'
    docker exec -u node $Container n8n import:workflow --input=$WorkflowPath
    if ($LASTEXITCODE -ne 0) { throw 'n8n workflow import failed.' }
    docker exec -u node $Container n8n export:workflow --all --output=$exportPath
    if ($LASTEXITCODE -ne 0) { throw 'n8n workflow export failed.' }
    $raw = docker exec -u node $Container cat $exportPath
    if ($LASTEXITCODE -ne 0 -or -not $raw) { throw 'Could not read n8n workflow export.' }
    $workflowId = Resolve-WorkflowId ($raw -join [Environment]::NewLine)
    Write-Host ('[n8n] Publishing workflow id=' + $workflowId)
    docker exec -u node $Container n8n publish:workflow --id=$workflowId
    if ($LASTEXITCODE -ne 0) { throw 'n8n workflow publish failed.' }
    docker restart $Container | Out-Null
    Wait-N8nReady
    Write-Host ('[n8n] JARVIS_WORKFLOW_PUBLISHED=' + $workflowId)
}

function Install-WorkflowNode {
    $nodeCommand = Get-Command node.exe -ErrorAction SilentlyContinue
    $node = if ($nodeCommand) { $nodeCommand.Source } else { Join-Path $env:ProgramFiles 'nodejs\node.exe' }
    $entry = Join-Path $NodeRuntimeDir 'node_modules\n8n\bin\n8n'
    $localWorkflow = Join-Path $PSScriptRoot 'workflows\jarvis-task-dispatcher.json'
    if (-not (Test-Path $node)) { throw 'Node executable was not found.' }
    if (-not (Test-Path $entry)) { throw 'Local n8n runtime is not installed.' }
    if (-not (Test-Path $localWorkflow)) { throw 'Jarvis workflow JSON was not found.' }
    New-Item -ItemType Directory -Force -Path $NodeUserDir | Out-Null
    $env:N8N_USER_FOLDER = $NodeUserDir
    $env:N8N_BLOCK_ENV_ACCESS_IN_NODE = 'false'
    $exportPath = Join-Path $env:TEMP 'openjarvis-workflows.json'
    Remove-Item $exportPath -Force -ErrorAction SilentlyContinue
    Write-Host '[n8n] Importing Jarvis workflow via local Node runtime'
    & $node $entry import:workflow --input=$localWorkflow
    if ($LASTEXITCODE -ne 0) { throw 'n8n workflow import failed.' }
    & $node $entry export:workflow --all --output=$exportPath
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $exportPath)) { throw 'n8n workflow export failed.' }
    $raw = Get-Content $exportPath -Raw
    $workflowId = Resolve-WorkflowId $raw
    Write-Host ('[n8n] Publishing workflow id=' + $workflowId)
    & $node $entry publish:workflow --id=$workflowId
    if ($LASTEXITCODE -ne 0) { throw 'n8n workflow publish failed.' }

    $listener = Get-NetTCPConnection -LocalPort 5678 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($listener) {
        $process = Get-CimInstance Win32_Process -Filter ("ProcessId=" + $listener.OwningProcess) -ErrorAction SilentlyContinue
        if ($process -and [string]$process.CommandLine -match 'n8n') {
            Stop-Process -Id $listener.OwningProcess -Force -ErrorAction SilentlyContinue
            Start-Sleep -Seconds 1
        }
    }

    & (Join-Path $PSScriptRoot 'start-n8n.ps1')
    if (-not $?) { throw 'Could not restart local n8n runtime.' }
    Wait-N8nReady
    Write-Host ('[n8n] JARVIS_WORKFLOW_PUBLISHED=' + $workflowId)
}

if (Test-DockerContainer) {
    Install-WorkflowDocker
} else {
    Install-WorkflowNode
}
