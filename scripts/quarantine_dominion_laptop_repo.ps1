param(
    [string]$RepoPath = 'C:\Users\Dell\dominion-ops'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Fail([string]$Reason) {
    Write-Host "LAPTOP_DRIFT_QUARANTINE=FAIL reason=$Reason"
    exit 1
}

if (-not (Get-Command git -ErrorAction SilentlyContinue)) { Fail 'git_missing' }
if (-not (Test-Path -LiteralPath (Join-Path $RepoPath '.git'))) { Fail 'repo_missing' }

Push-Location $RepoPath
try {
    $unmerged = @(& git ls-files -u)
    if ($LASTEXITCODE -ne 0) { Fail 'unmerged_check_failed' }
    if ($unmerged.Count -gt 0) {
        Write-Host "LAPTOP_DRIFT_QUARANTINE=HOLD unmerged=$($unmerged.Count)"
        Fail 'unmerged_paths'
    }

    $status = @(& git status --porcelain=v1 --untracked-files=all)
    if ($LASTEXITCODE -ne 0) { Fail 'status_failed' }
    if ($status.Count -eq 0) {
        Write-Host 'LAPTOP_DRIFT_QUARANTINE=PASS state=clean tracked=0 untracked=0 stash=none'
        exit 0
    }

    $tracked = @($status | Where-Object { -not $_.StartsWith('??') })
    $untracked = @($status | Where-Object { $_.StartsWith('??') })
    $runId = if ($env:GITHUB_RUN_ID) { $env:GITHUB_RUN_ID } else { [DateTimeOffset]::UtcNow.ToUnixTimeSeconds().ToString() }
    $message = "dominion-parity-quarantine-$runId"

    & git stash push --include-untracked --message $message | Out-Null
    if ($LASTEXITCODE -ne 0) { Fail 'stash_failed' }

    $post = @(& git status --porcelain=v1 --untracked-files=all)
    if ($LASTEXITCODE -ne 0) { Fail 'post_stash_status_failed' }
    if ($post.Count -gt 0) { Fail 'post_stash_repo_dirty' }

    $stashSha = (& git rev-parse refs/stash).Trim().ToLowerInvariant()
    if ($LASTEXITCODE -ne 0 -or $stashSha -notmatch '^[0-9a-f]{40}$') { Fail 'stash_sha_unreadable' }

    Write-Host "LAPTOP_DRIFT_QUARANTINE=PASS state=quarantined tracked=$($tracked.Count) untracked=$($untracked.Count) stash=$stashSha"
} finally {
    Pop-Location
}
