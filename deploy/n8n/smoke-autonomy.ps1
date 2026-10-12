param(
    [string]$OpenJarvisBaseUrl = 'http://127.0.0.1:8000',
    [string]$N8nBaseUrl = 'http://127.0.0.1:5678',
    [string]$Workspace = 'C:\Users\chris\source\repos\OpenJarvis',
    [string]$RuntimeDeviceId = '',
    [string]$ApiKey = '',
    [string]$SmokeModel = 'llama3.2:1b',
    [int]$MaxPolls = 40
)

$ErrorActionPreference = 'Stop'

function Invoke-JarvisRequest {
    param(
        [string]$Method,
        [string]$Uri,
        [object]$Body = $null
    )
    $headers = @{}
    if ($ApiKey) { $headers.Authorization = "Bearer $ApiKey" }
    $params = @{ Method = $Method; Uri = $Uri; Headers = $headers; TimeoutSec = 10 }
    if ($null -ne $Body) {
        $params.ContentType = 'application/json'
        $params.Body = ($Body | ConvertTo-Json -Depth 12 -Compress)
    }
    return Invoke-RestMethod @params
}

Write-Host '[smoke] OpenJarvis health'
$health = Invoke-JarvisRequest -Method GET -Uri "$OpenJarvisBaseUrl/health"
if ($health.status -ne 'ok') { throw 'OpenJarvis health is not ok.' }

Write-Host '[smoke] n8n reachability'
$n8n = Invoke-WebRequest -Uri "$N8nBaseUrl/healthz" -UseBasicParsing -TimeoutSec 10
if ($n8n.StatusCode -lt 200 -or $n8n.StatusCode -ge 500) {
    throw "n8n returned status $($n8n.StatusCode)."
}

$context = @{
    workspace = $Workspace
    branch = 'main'
    smoke = $true
    model = $SmokeModel
    mcpToolAllowlist = @('list_directory')
}
if ($RuntimeDeviceId) { $context.runtimeDeviceId = $RuntimeDeviceId }

$payload = @{
    goal = ("EXACT WINDOWS WORKSPACE: $Workspace. Use exact absolute Windows paths " +
        "from this instruction. lista el contenido del workspace usando list_directory. " +
        "No modifiques ningun archivo.")
    project = 'OpenJarvis'
    workflow = 'auto'
    approval = 'risk_based'
    context = $context
}

Write-Host '[smoke] create autonomy task'
$task = Invoke-JarvisRequest -Method POST -Uri "$OpenJarvisBaseUrl/v1/autonomy/tasks" -Body $payload
$taskId = [string]$task.taskId
if (-not $taskId) { throw 'Autonomy taskId was not returned.' }
Write-Host ("[smoke] taskId=" + $taskId)

for ($i = 1; $i -le $MaxPolls; $i++) {
    Start-Sleep -Seconds 3
    $current = Invoke-JarvisRequest -Method GET -Uri "$OpenJarvisBaseUrl/v1/autonomy/tasks/$taskId"
    Write-Host ("[smoke] poll=" + $i + " status=" + $current.status + " checkpoint=" + $current.checkpoint)
    if ($current.status -eq 'completed') {
        if ($current.context.resultCallbackDelivered -ne $true) {
            $current | ConvertTo-Json -Depth 20
            throw 'Autonomy completed but the n8n result callback was not verified.'
        }
        Write-Host '[smoke] AUTONOMY_V2_RESULT_CALLBACK=PASS'
        Write-Host '[smoke] AUTONOMY_V2_SMOKE=PASS'
        $current | ConvertTo-Json -Depth 20
        exit 0
    }
    if ($current.status -in @('failed', 'cancelled', 'blocked')) {
        $current | ConvertTo-Json -Depth 20
        throw "Autonomy task ended with status $($current.status)."
    }
}

$last = Invoke-JarvisRequest -Method GET -Uri "$OpenJarvisBaseUrl/v1/autonomy/tasks/$taskId"
$last | ConvertTo-Json -Depth 20
throw 'Autonomy smoke did not reach completed status within the poll budget.'
