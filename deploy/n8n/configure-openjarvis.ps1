param(
    [string]$WebhookUrl = 'http://127.0.0.1:5678/webhook/jarvis/task',
    [string]$RuntimeCmd = "$env:USERPROFILE\.openjarvis\start-runtime.cmd"
)

$ErrorActionPreference = 'Stop'

[Environment]::SetEnvironmentVariable(
    'OPENJARVIS_N8N_WEBHOOK_URL',
    $WebhookUrl,
    'User'
)
$env:OPENJARVIS_N8N_WEBHOOK_URL = $WebhookUrl

if (Test-Path $RuntimeCmd) {
    $content = Get-Content $RuntimeCmd -Raw
    $line = "set `"OPENJARVIS_N8N_WEBHOOK_URL=$WebhookUrl`""
    if ($content -match '(?m)^set "OPENJARVIS_N8N_WEBHOOK_URL=.*"\r?$') {
        $content = [regex]::Replace(
            $content,
            '(?m)^set "OPENJARVIS_N8N_WEBHOOK_URL=.*"\r?$',
            $line
        )
    } elseif ($content -match '(?m)^set "JARVIS_NUM_CTX=.*"\r?$') {
        $content = [regex]::Replace(
            $content,
            '(?m)^(set "JARVIS_NUM_CTX=.*"\r?$)',
            "`$1`r`n$line",
            1
        )
    } else {
        $content = $content.TrimEnd() + "`r`n$line`r`n"
    }
    Set-Content -Path $RuntimeCmd -Value $content -Encoding ASCII
}

Write-Host ('OPENJARVIS_N8N_WEBHOOK_URL=' + $WebhookUrl)
Write-Host '[n8n] OpenJarvis runtime environment configured.'
