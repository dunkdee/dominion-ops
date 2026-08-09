param(
    [Parameter(Mandatory = $true)]
    [string]$ExpectedSha,
    [Parameter(Mandatory = $true)]
    [string]$BundlePath,
    [string]$RepoPath = 'C:\Users\Dell\dominion-ops',
    [string]$VaultRoot = 'C:\Users\Dell\Documents\Dominion Command Vault'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Fail([string]$Reason) {
    Write-Host "LAPTOP_SYNC=FAIL reason=$Reason"
    exit 1
}

if ($ExpectedSha -notmatch '^[0-9a-fA-F]{40}$') { Fail 'invalid_expected_sha' }
if (-not (Get-Command git -ErrorAction SilentlyContinue)) { Fail 'git_missing' }
if (-not (Test-Path -LiteralPath (Join-Path $RepoPath '.git'))) { Fail 'repo_missing' }
if (-not (Test-Path -LiteralPath $BundlePath -PathType Leaf)) { Fail 'bundle_missing' }
$bundleItem = Get-Item -LiteralPath $BundlePath -Force
if ($bundleItem.Attributes -band [IO.FileAttributes]::ReparsePoint) { Fail 'bundle_symlink_or_reparse' }

Push-Location $RepoPath
try {
    $origin = (& git remote get-url origin).Trim()
    if ($LASTEXITCODE -ne 0) { Fail 'origin_unreadable' }
    $normalized = ($origin -replace '\.git$','').ToLowerInvariant()
    if ($normalized -notmatch 'github\.com[:/]dunkdee/dominion-ops$') { Fail 'origin_mismatch' }

    $status = @(& git status --porcelain=v1 --untracked-files=all)
    if ($LASTEXITCODE -ne 0) { Fail 'status_failed' }
    if ($status.Count -gt 0) {
        $unmerged = @(& git ls-files -u)
        $tracked = @($status | Where-Object { -not $_.StartsWith('??') })
        $untracked = @($status | Where-Object { $_.StartsWith('??') })
        Write-Host "LAPTOP_PARITY_HOLD tracked=$($tracked.Count) untracked=$($untracked.Count) unmerged=$($unmerged.Count)"
        Fail 'laptop_repo_dirty'
    }

    & git bundle verify $BundlePath
    if ($LASTEXITCODE -ne 0) { Fail 'bundle_verify_failed' }
    & git fetch --force $BundlePath 'refs/heads/dominion-release:refs/remotes/dominion-release/main'
    if ($LASTEXITCODE -ne 0) { Fail 'bundle_fetch_failed' }

    $releaseSha = (& git rev-parse 'refs/remotes/dominion-release/main').Trim().ToLowerInvariant()
    if ($LASTEXITCODE -ne 0) { Fail 'bundle_release_ref_unreadable' }
    if ($releaseSha -ne $ExpectedSha.ToLowerInvariant()) {
        Write-Host "LAPTOP_PARITY_HOLD expected=$ExpectedSha bundle_sha=$releaseSha"
        Fail 'bundle_sha_mismatch'
    }

    & git merge-base --is-ancestor HEAD $ExpectedSha
    if ($LASTEXITCODE -ne 0) { Fail 'non_fast_forward_laptop_repo' }

    & git checkout main
    if ($LASTEXITCODE -ne 0) { Fail 'checkout_main_failed' }
    & git merge --ff-only $ExpectedSha
    if ($LASTEXITCODE -ne 0) { Fail 'fast_forward_failed' }

    $head = (& git rev-parse HEAD).Trim().ToLowerInvariant()
    if ($head -ne $ExpectedSha.ToLowerInvariant()) { Fail 'post_sync_sha_mismatch' }
    $postStatus = @(& git status --porcelain=v1 --untracked-files=all)
    if ($postStatus.Count -gt 0) { Fail 'post_sync_repo_dirty' }

    $python = $null
    if (Get-Command py -ErrorAction SilentlyContinue) {
        $python = @('py','-3')
    } elseif (Get-Command python -ErrorAction SilentlyContinue) {
        $python = @('python')
    } else {
        Fail 'python_missing'
    }

    if (-not (Test-Path -LiteralPath $VaultRoot)) {
        New-Item -ItemType Directory -Path $VaultRoot -Force | Out-Null
    }
    $vaultItem = Get-Item -LiteralPath $VaultRoot -Force
    if ($vaultItem.Attributes -band [IO.FileAttributes]::ReparsePoint) { Fail 'vault_root_symlink_or_reparse' }

    $runId = if ($env:GITHUB_RUN_ID) { $env:GITHUB_RUN_ID } else { [DateTimeOffset]::UtcNow.ToUnixTimeSeconds().ToString() }
    $current = Join-Path $VaultRoot 'Dominion-Brain'
    $stage = Join-Path $VaultRoot ".dominion-brain-stage-$($ExpectedSha.Substring(0,12))-$runId"
    $backup = Join-Path $VaultRoot ".dominion-brain-backup-$runId"
    if (Test-Path -LiteralPath $stage) { Fail 'staging_collision' }
    if (Test-Path -LiteralPath $backup) { Fail 'backup_collision' }

    $published = $false
    $oldPresent = $false
    try {
        if ($python[0] -eq 'py') {
            & py -3 scripts/render_dominion_brain.py $stage
        } else {
            & python scripts/render_dominion_brain.py $stage
        }
        if ($LASTEXITCODE -ne 0) { throw 'render_failed' }

        $manifestPath = Join-Path $stage 'MANIFEST.json'
        if (-not (Test-Path -LiteralPath $manifestPath)) { throw 'manifest_missing' }
        $manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
        if ($manifest.schema -ne 'dominion-brain-manifest-v2') { throw 'manifest_schema' }
        if ([int]$manifest.agent_count -le 0) { throw 'agent_count' }
        $brainDigest = [string]$manifest.source_revision.sha256
        if ($brainDigest -notmatch '^[0-9a-f]{64}$') { throw 'brain_digest' }

        foreach ($entry in $manifest.files) {
            $filePath = Join-Path $stage ([string]$entry.path)
            if (-not (Test-Path -LiteralPath $filePath)) { throw 'manifest_file_missing' }
            $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $filePath).Hash.ToLowerInvariant()
            if ($hash -ne ([string]$entry.sha256).ToLowerInvariant()) { throw 'manifest_hash_mismatch' }
        }

        if (Test-Path -LiteralPath $current) {
            $currentItem = Get-Item -LiteralPath $current -Force
            if (-not $currentItem.PSIsContainer -or ($currentItem.Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw 'current_not_safe_directory' }
            Move-Item -LiteralPath $current -Destination $backup
            $oldPresent = $true
        }
        Move-Item -LiteralPath $stage -Destination $current
        $published = $true

        $receiptRoot = Join-Path $VaultRoot 'Dominion-Release-State'
        if (-not (Test-Path -LiteralPath $receiptRoot)) { New-Item -ItemType Directory -Path $receiptRoot -Force | Out-Null }
        $receipt = [ordered]@{
            schema = 'dominion-three-node-parity-v1'
            node = 'laptop'
            repository = 'dunkdee/dominion-ops'
            git_sha = $head
            brain_source_digest = $brainDigest
            agent_count = [int]$manifest.agent_count
            recorded_at_utc = [DateTime]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ssZ')
        } | ConvertTo-Json -Depth 4
        $receiptTmp = Join-Path $receiptRoot ('.latest-' + [Guid]::NewGuid().ToString('N') + '.tmp')
        [IO.File]::WriteAllText($receiptTmp, $receipt + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
        Move-Item -LiteralPath $receiptTmp -Destination (Join-Path $receiptRoot 'laptop-latest.json') -Force

        Write-Host "LAPTOP_SYNC=PASS git_sha=$head brain_digest=$brainDigest agents=$($manifest.agent_count)"
    } catch {
        if ($published -and (Test-Path -LiteralPath $current)) {
            Remove-Item -LiteralPath $current -Recurse -Force
        }
        if ($oldPresent -and (Test-Path -LiteralPath $backup)) {
            Move-Item -LiteralPath $backup -Destination $current
        }
        if (Test-Path -LiteralPath $stage) { Remove-Item -LiteralPath $stage -Recurse -Force }
        Fail ('brain_publish_' + ($_.Exception.Message -replace '[^A-Za-z0-9_.-]','_'))
    }
} finally {
    Pop-Location
}
