param(
    [string]$WebhookUrl = 'http://127.0.0.1:5678/webhook/jarvis/task',
    [string]$ResultWebhookUrl = 'http://127.0.0.1:5678/webhook/jarvis/result',
    [string]$RuntimeCmd = "$env:USERPROFILE\.openjarvis\start-runtime.cmd"
)

$ErrorActionPreference = 'Stop'

[Environment]::SetEnvironmentVariable(
    'OPENJARVIS_N8N_WEBHOOK_URL',
    $WebhookUrl,
    'User'
)
$env:OPENJARVIS_N8N_WEBHOOK_URL = $WebhookUrl

[Environment]::SetEnvironmentVariable(
    'OPENJARVIS_N8N_RESULT_WEBHOOK_URL',
    $ResultWebhookUrl,
    'User'
)
$env:OPENJARVIS_N8N_RESULT_WEBHOOK_URL = $ResultWebhookUrl

if (Test-Path $RuntimeCmd) {
    $content = Get-Content $RuntimeCmd -Raw
    $taskLine = "set `"OPENJARVIS_N8N_WEBHOOK_URL=$WebhookUrl`""
    $resultLine = "set `"OPENJARVIS_N8N_RESULT_WEBHOOK_URL=$ResultWebhookUrl`""

    if ($content -match '(?m)^set "OPENJARVIS_N8N_WEBHOOK_URL=.*"?$') {
        $content = [regex]::Replace(
            $content,
            '(?m)^set "OPENJARVIS_N8N_WEBHOOK_URL=.*"?$',
            $taskLine
        )
    } elseif ($content -match '(?m)^set "JARVIS_NUM_CTX=.*"?$') {
        $content = [regex]::Replace(
            $content,
            '(?m)^(set "JARVIS_NUM_CTX=.*"?$)',
            "`$1`r`n$taskLine",
            1
        )
    } else {
        $content = $content.TrimEnd() + "`r`n$taskLine`r`n"
    }

    if ($content -match '(?m)^set "OPENJARVIS_N8N_RESULT_WEBHOOK_URL=.*"?$') {
        $content = [regex]::Replace(
            $content,
            '(?m)^set "OPENJARVIS_N8N_RESULT_WEBHOOK_URL=.*"?$',
            $resultLine
        )
    } elseif ($content -match '(?m)^set "OPENJARVIS_N8N_WEBHOOK_URL=.*"?$') {
        $content = [regex]::Replace(
            $content,
            '(?m)^(set "OPENJARVIS_N8N_WEBHOOK_URL=.*"?$)',
            "`$1`r`n$resultLine",
            1
        )
    } else {
        $content = $content.TrimEnd() + "`r`n$resultLine`r`n"
    }

    Set-Content -Path $RuntimeCmd -Value $content -Encoding ASCII
}

Write-Host ('OPENJARVIS_N8N_WEBHOOK_URL=' + $WebhookUrl)
Write-Host ('OPENJARVIS_N8N_RESULT_WEBHOOK_URL=' + $ResultWebhookUrl)
Write-Host '[n8n] OpenJarvis runtime environment configured.'
