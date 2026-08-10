param(
    [Parameter(Mandatory = $true)]
    [string]$ExpectedSha,
    [Parameter(Mandatory = $true)]
    [string]$ExpectedBrainDigest,
    [Parameter(Mandatory = $true)]
    [string]$BundlePath,
    [Parameter(Mandatory = $true)]
    [string]$BrainSourcePath,
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
if ($ExpectedBrainDigest -notmatch '^[0-9a-fA-F]{64}$') { Fail 'invalid_expected_brain_digest' }
if (-not (Get-Command git -ErrorAction SilentlyContinue)) { Fail 'git_missing' }
if (-not (Test-Path -LiteralPath (Join-Path $RepoPath '.git'))) { Fail 'repo_missing' }
if (-not (Test-Path -LiteralPath $BundlePath -PathType Leaf)) { Fail 'bundle_missing' }
if (-not (Test-Path -LiteralPath $BrainSourcePath -PathType Container)) { Fail 'brain_artifact_missing' }
$bundleItem = Get-Item -LiteralPath $BundlePath -Force
$brainSourceItem = Get-Item -LiteralPath $BrainSourcePath -Force
if ($bundleItem.Attributes -band [IO.FileAttributes]::ReparsePoint) { Fail 'bundle_symlink_or_reparse' }
if ($brainSourceItem.Attributes -band [IO.FileAttributes]::ReparsePoint) { Fail 'brain_artifact_symlink_or_reparse' }
if (Get-ChildItem -LiteralPath $BrainSourcePath -Recurse -Force | Where-Object { $_.Attributes -band [IO.FileAttributes]::ReparsePoint }) { Fail 'brain_artifact_contains_reparse' }

Push-Location $RepoPath
try {
    $origin = (& git remote get-url origin).Trim()
    if ($LASTEXITCODE -ne 0) { Fail 'origin_unreadable' }
    $normalized = (($origin -replace '\.git$','').TrimEnd('/')).ToLowerInvariant()
    $allowedOrigins = @(
        'https://github.com/dunkdee/dominion-ops',
        'git@github.com:dunkdee/dominion-ops',
        'ssh://git@github.com/dunkdee/dominion-ops'
    )
    if ($allowedOrigins -notcontains $normalized) { Fail 'origin_mismatch' }

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

    & git checkout main
    if ($LASTEXITCODE -ne 0) { Fail 'checkout_main_failed' }
    & git merge-base --is-ancestor HEAD $ExpectedSha
    if ($LASTEXITCODE -ne 0) { Fail 'non_fast_forward_laptop_repo' }
    & git merge --ff-only $ExpectedSha
    if ($LASTEXITCODE -ne 0) { Fail 'fast_forward_failed' }

    $head = (& git rev-parse HEAD).Trim().ToLowerInvariant()
    if ($head -ne $ExpectedSha.ToLowerInvariant()) { Fail 'post_sync_sha_mismatch' }
    $postStatus = @(& git status --porcelain=v1 --untracked-files=all)
    if ($postStatus.Count -gt 0) { Fail 'post_sync_repo_dirty' }

    if (-not (Test-Path -LiteralPath $VaultRoot)) {
        New-Item -ItemType Directory -Path $VaultRoot -Force | Out-Null
    }
    $vaultItem = Get-Item -LiteralPath $VaultRoot -Force
    if (-not $vaultItem.PSIsContainer) { Fail 'vault_root_not_directory' }
    if ($vaultItem.Attributes -band [IO.FileAttributes]::ReparsePoint) { Fail 'vault_root_symlink_or_reparse' }

    $runId = if ($env:GITHUB_RUN_ID) { $env:GITHUB_RUN_ID } else { [DateTimeOffset]::UtcNow.ToUnixTimeSeconds().ToString() }
    $runAttempt = if ($env:GITHUB_RUN_ATTEMPT) { $env:GITHUB_RUN_ATTEMPT } else { '1' }
    $releaseId = "$runId-$runAttempt"
    $current = Join-Path $VaultRoot 'Dominion-Brain'
    $stage = Join-Path $VaultRoot ".dominion-brain-stage-$($ExpectedSha.Substring(0,12))-$releaseId"
    $backup = Join-Path $VaultRoot ".dominion-brain-backup-$releaseId"
    if (Test-Path -LiteralPath $stage) { Fail 'staging_collision' }
    if (Test-Path -LiteralPath $backup) { Fail 'backup_collision' }

    $published = $false
    $oldPresent = $false
    try {
        New-Item -ItemType Directory -Path $stage | Out-Null
        Get-ChildItem -LiteralPath $BrainSourcePath -Force | ForEach-Object {
            Copy-Item -LiteralPath $_.FullName -Destination $stage -Recurse -Force
        }

        $manifestPath = Join-Path $stage 'MANIFEST.json'
        if (-not (Test-Path -LiteralPath $manifestPath)) { throw 'manifest_missing' }
        $manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
        if ($manifest.schema -ne 'dominion-brain-manifest-v2') { throw 'manifest_schema' }
        if ([int]$manifest.agent_count -le 0) { throw 'agent_count' }
        if (@($manifest.files).Count -le 0) { throw 'manifest_files_empty' }
        $brainDigest = ([string]$manifest.source_revision.sha256).ToLowerInvariant()
        if ($brainDigest -notmatch '^[0-9a-f]{64}$') { throw 'brain_digest' }
        if ($brainDigest -ne $ExpectedBrainDigest.ToLowerInvariant()) { throw 'canonical_brain_digest_mismatch' }

        foreach ($entry in $manifest.files) {
            $relative = [string]$entry.path
            if ([IO.Path]::IsPathRooted($relative) -or $relative -match '(^|[\\/])\.\.([\\/]|$)') { throw 'unsafe_manifest_path' }
            $filePath = Join-Path $stage $relative
            if (-not (Test-Path -LiteralPath $filePath -PathType Leaf)) { throw 'manifest_file_missing' }
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
        $receiptRootItem = Get-Item -LiteralPath $receiptRoot -Force
        if (-not $receiptRootItem.PSIsContainer -or ($receiptRootItem.Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw 'receipt_root_not_safe_directory' }
        $receipt = [ordered]@{
            schema = 'dominion-three-node-parity-v1'
            node = 'laptop'
            repository = 'dunkdee/dominion-ops'
            git_sha = $head
            brain_source_digest = $brainDigest
            canonical_brain_source_digest = $ExpectedBrainDigest.ToLowerInvariant()
            agent_count = [int]$manifest.agent_count
            recorded_at_utc = [DateTime]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ssZ')
        } | ConvertTo-Json -Depth 4
        $receiptTmp = Join-Path $receiptRoot ('.latest-' + [Guid]::NewGuid().ToString('N') + '.tmp')
        [IO.File]::WriteAllText($receiptTmp, $receipt + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
        Move-Item -LiteralPath $receiptTmp -Destination (Join-Path $receiptRoot 'laptop-latest.json') -Force

        Write-Host "LAPTOP_SYNC=PASS git_sha=$head brain_digest=$brainDigest agents=$($manifest.agent_count)"
    } catch {
        $originalError = [string]$_.Exception.Message
        $rollbackIssues = New-Object System.Collections.Generic.List[string]

        if ($published -and (Test-Path -LiteralPath $current)) {
            try { Remove-Item -LiteralPath $current -Recurse -Force -ErrorAction Stop }
            catch { $rollbackIssues.Add('remove_current') }
        }
        if ($oldPresent -and (Test-Path -LiteralPath $backup)) {
            try { Move-Item -LiteralPath $backup -Destination $current -ErrorAction Stop }
            catch { $rollbackIssues.Add('restore_backup') }
        }
        if (Test-Path -LiteralPath $stage) {
            try { Remove-Item -LiteralPath $stage -Recurse -Force -ErrorAction Stop }
            catch { $rollbackIssues.Add('remove_stage') }
        }

        if ($rollbackIssues.Count -eq 0) {
            Write-Host 'LAPTOP_SYNC_ROLLBACK=PASS'
        } else {
            Write-Host ("LAPTOP_SYNC_ROLLBACK=HOLD issues=" + (($rollbackIssues | Sort-Object -Unique) -join ','))
        }
        $safeError = ($originalError -replace '[^A-Za-z0-9_.-]','_')
        if ([string]::IsNullOrWhiteSpace($safeError)) { $safeError = 'unknown' }
        Fail ('brain_publish_' + $safeError)
    }
} finally {
    Pop-Location
}
