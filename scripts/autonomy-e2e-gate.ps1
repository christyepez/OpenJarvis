param(
    [string]$Repo = "C:\Users\chris\source\repos\OpenJarvis"
)

$ErrorActionPreference = "Stop"
Set-Location $Repo

$target = Join-Path $Repo "docs\operations\autonomy-e2e.md"
if (-not (Test-Path $target)) {
    Write-Error "[E2E] target file missing: $target"
    exit 10
}

$expected = "JARVIS AUTONOMY E2E FINAL OK"
$actual = (Get-Content $target -Raw).Trim()
if ($actual -ne $expected) {
    Write-Error "[E2E] target content mismatch"
    exit 11
}
Write-Output "[E2E] write_file=ok"

& ".\.venv\Scripts\python.exe" -m pytest "tests\agents\test_operative_persistence.py" -q
if ($LASTEXITCODE -ne 0) {
    Write-Error "[E2E] pytest failed"
    exit $LASTEXITCODE
}
Write-Output "[E2E] pytest=ok"

git diff --check
if ($LASTEXITCODE -ne 0) {
    Write-Error "[E2E] git diff --check failed"
    exit $LASTEXITCODE
}
Write-Output "[E2E] git_diff_check=ok"

git add -- "docs/operations/autonomy-e2e.md"
if ($LASTEXITCODE -ne 0) {
    Write-Error "[E2E] git add failed"
    exit $LASTEXITCODE
}

$alreadyCommitted = $false
git diff --cached --quiet -- "docs/operations/autonomy-e2e.md"
if ($LASTEXITCODE -eq 0) {
    $headContent = git show "HEAD:docs/operations/autonomy-e2e.md" 2>$null
    if ($LASTEXITCODE -ne 0 -or ($headContent -join "`n").Trim() -ne $expected) {
        Write-Error "[E2E] target produced no staged change and HEAD does not contain expected marker"
        exit 12
    }

    git fetch origin main --quiet
    if ($LASTEXITCODE -ne 0) {
        Write-Error "[E2E] fetch failed while verifying idempotent state"
        exit $LASTEXITCODE
    }
    $headSha = (git rev-parse HEAD).Trim()
    $originSha = (git rev-parse origin/main).Trim()
    if ($headSha -ne $originSha) {
        Write-Error "[E2E] expected marker is committed locally but not synchronized to origin/main"
        exit 13
    }

    $alreadyCommitted = $true
    Write-Output "[E2E] commit=already-ok"
    Write-Output "[E2E] push=already-ok"
}

if (-not $alreadyCommitted) {
    git commit -m "test: validate autonomous e2e" -- "docs/operations/autonomy-e2e.md"
    if ($LASTEXITCODE -ne 0) {
        Write-Error "[E2E] commit failed"
        exit $LASTEXITCODE
    }
    Write-Output "[E2E] commit=ok"

    git push origin main
    if ($LASTEXITCODE -ne 0) {
        Write-Error "[E2E] push failed"
        exit $LASTEXITCODE
    }
    Write-Output "[E2E] push=ok"
}

Write-Output "[E2E] git_log:"
git log -1 --oneline
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Output "[E2E] git_status:"
git status --short
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Output "[E2E] AUTONOMY_GATE_OK"
Write-Output "[E2E] Process completed with exit code 0"
exit 0
