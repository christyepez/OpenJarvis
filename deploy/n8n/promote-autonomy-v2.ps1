param(
    [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path,
    [string]$RuntimeDeviceId = '',
    [switch]$SkipBootstrap,
    [switch]$CreateCommit
)

$ErrorActionPreference = 'Stop'
$versionFile = Join-Path $RepoRoot 'src\openjarvis\autonomy\version.py'
$bootstrap = Join-Path $PSScriptRoot 'bootstrap-autonomy-v2.ps1'

function Assert-CleanPromotionScope {
    $dirty = git -C $RepoRoot status --porcelain --untracked-files=no
    if ($LASTEXITCODE -ne 0) { throw 'git status failed.' }
    if ($dirty) {
        throw 'Stable promotion requires a clean working tree.'
    }
}

function Assert-ReleaseCandidate {
    $content = Get-Content $versionFile -Raw
    if ($content -notmatch 'AUTONOMY_V2_VERSION\s*=\s*"2\.0\.0-rc[0-9]+"') {
        throw 'Current Autonomy V2 version is not a 2.0.0 release candidate.'
    }
}

Assert-CleanPromotionScope
Assert-ReleaseCandidate

if (-not $SkipBootstrap) {
    Write-Host '[promote] Running real Autonomy V2 bootstrap + smoke gate'
    & $bootstrap -RuntimeDeviceId $RuntimeDeviceId
    if (-not $?) {
        throw 'Autonomy V2 bootstrap gate failed.'
    }
}

Write-Host '[promote] Running focused Autonomy V2 test suite'
Push-Location $RepoRoot
try {
    uv run pytest tests/autonomy tests/server/test_autonomy_routes.py tests/speech/test_voice_control.py -q --tb=short
    if ($LASTEXITCODE -ne 0) {
        throw 'Autonomy V2 focused tests failed.'
    }

    uv run ruff check src/openjarvis/autonomy src/openjarvis/server/autonomy_routes.py src/openjarvis/speech/voice_control.py tests/autonomy tests/server/test_autonomy_routes.py tests/speech/test_voice_control.py
    if ($LASTEXITCODE -ne 0) {
        throw 'Autonomy V2 lint gate failed.'
    }

    $dockerAvailable = $false
    try {
        docker info *> $null
        $dockerAvailable = ($LASTEXITCODE -eq 0)
    }
    catch {
        $dockerAvailable = $false
    }

    if ($dockerAvailable) {
        docker compose -f deploy/n8n/docker-compose.yml config | Out-Null
        if ($LASTEXITCODE -ne 0) {
            throw 'n8n compose validation failed.'
        }
    }
    else {
        Write-Host '[promote] Docker unavailable; validating local Node n8n fallback'
        $nodeRuntime = Join-Path $env:USERPROFILE '.openjarvis\n8n-runtime\node_modules\n8n\bin\n8n'
        $workflow = Join-Path $RepoRoot 'deploy\n8n\workflows\jarvis-task-dispatcher.json'
        if (-not (Test-Path $nodeRuntime)) {
            throw 'Local Node n8n runtime is not installed.'
        }
        if (-not (Test-Path $workflow)) {
            throw 'Jarvis n8n workflow JSON was not found.'
        }
        Get-Content $workflow -Raw | ConvertFrom-Json | Out-Null
    }

    Write-Host '[promote] All stable gates passed; updating version to 2.0.0'
    Set-Content -Path $versionFile -Value 'AUTONOMY_V2_VERSION = "2.0.0"' -Encoding UTF8

    git diff --check
    if ($LASTEXITCODE -ne 0) {
        throw 'git diff --check failed after version promotion.'
    }

    if ($CreateCommit) {
        git add -- $versionFile
        git commit -m 'release: promote Autonomy V2 to 2.0.0'
        if ($LASTEXITCODE -ne 0) {
            throw 'Stable promotion commit failed.'
        }
        Write-Host '[promote] AUTONOMY_V2_STABLE_COMMIT=PASS'
    }
}
finally {
    Pop-Location
}

Write-Host '[promote] AUTONOMY_V2_STABLE=PASS'
