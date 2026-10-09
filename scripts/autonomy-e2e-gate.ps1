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

$expected = "JARVIS AUTONOMY E2E OK"
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

git diff --cached --quiet -- "docs/operations/autonomy-e2e.md"
if ($LASTEXITCODE -eq 0) {
    Write-Error "[E2E] target produced no staged change"
    exit 12
}

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

Write-Output "[E2E] git_log:"
git log -1 --oneline
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Output "[E2E] git_status:"
git status --short
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Output "[E2E] AUTONOMY_GATE_OK"
exit 0
