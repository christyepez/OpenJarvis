param(
    [string]$Container = 'openjarvis-n8n',
    [string]$WorkflowPath = '/workflows/jarvis-task-dispatcher.json',
    [string]$WorkflowName = 'Jarvis Task Dispatcher'
)

$ErrorActionPreference = 'Stop'
$exportPath = '/tmp/openjarvis-workflows.json'

Write-Host '[n8n] Importing Jarvis workflow'
docker exec -u node $Container n8n import:workflow --input=$WorkflowPath
if ($LASTEXITCODE -ne 0) { throw 'n8n workflow import failed.' }

Write-Host '[n8n] Resolving imported workflow id'
docker exec -u node $Container n8n export:workflow --all --output=$exportPath
if ($LASTEXITCODE -ne 0) { throw 'n8n workflow export failed.' }

$raw = docker exec -u node $Container cat $exportPath
if ($LASTEXITCODE -ne 0 -or -not $raw) { throw 'Could not read n8n workflow export.' }

$items = $raw | ConvertFrom-Json
if ($items -isnot [System.Collections.IEnumerable] -or $items -is [string]) {
    $items = @($items)
}
$workflow = @($items) | Where-Object { $_.name -eq $WorkflowName } | Select-Object -First 1
if (-not $workflow -or -not $workflow.id) {
    throw "Imported workflow '$WorkflowName' was not found."
}
$workflowId = [string]$workflow.id
Write-Host ("[n8n] Publishing workflow id=" + $workflowId)
docker exec -u node $Container n8n publish:workflow --id=$workflowId
if ($LASTEXITCODE -ne 0) { throw 'n8n workflow publish failed.' }

Write-Host '[n8n] Restarting container so published state takes effect'
docker restart $Container | Out-Null

$deadline = (Get-Date).AddSeconds(60)
do {
    Start-Sleep -Seconds 2
    try {
        $response = Invoke-WebRequest -Uri 'http://127.0.0.1:5678/' -UseBasicParsing -TimeoutSec 3
        if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500) {
            Write-Host ('[n8n] JARVIS_WORKFLOW_PUBLISHED=' + $workflowId)
            exit 0
        }
    } catch {
        # n8n may still be restarting.
    }
} while ((Get-Date) -lt $deadline)

throw 'n8n did not become reachable after workflow publish.'
