param(
    [string]$RepoPath = 'C:\Users\Dell\dominion-ops',
    [string]$VaultRoot = 'C:\Users\Dell\Documents\Dominion Command Vault',
    [string]$InstallRoot = 'C:\actions-runner'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Fail([string]$Reason) {
    Write-Host "LAPTOP_RUNNER_ACL_REPAIR=HOLD reason=$Reason"
    exit 1
}

function Is-Administrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]::new($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Assert-SafeDirectory([string]$Path, [string]$ReasonPrefix) {
    if (-not (Test-Path -LiteralPath $Path -PathType Container)) { Fail ($ReasonPrefix + '_missing') }
    $item = Get-Item -LiteralPath $Path -Force
    if (-not $item.PSIsContainer) { Fail ($ReasonPrefix + '_not_directory') }
    if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { Fail ($ReasonPrefix + '_reparse_point') }
}

if (-not (Is-Administrator)) { Fail 'administrator_required' }
if (-not (Get-Command git -ErrorAction SilentlyContinue)) { Fail 'git_missing' }
if (-not (Get-Command icacls.exe -ErrorAction SilentlyContinue)) { Fail 'icacls_missing' }

Assert-SafeDirectory -Path $RepoPath -ReasonPrefix 'repo'
if (-not (Test-Path -LiteralPath (Join-Path $RepoPath '.git'))) { Fail 'repo_git_missing' }
Assert-SafeDirectory -Path $InstallRoot -ReasonPrefix 'runner_install_root'

if (-not (Test-Path -LiteralPath $VaultRoot)) {
    New-Item -ItemType Directory -Path $VaultRoot -Force | Out-Null
}
Assert-SafeDirectory -Path $VaultRoot -ReasonPrefix 'vault_root'

$escapedInstallRoot = [regex]::Escape($InstallRoot)
$services = @(Get-CimInstance Win32_Service | Where-Object {
    $_.Name -like 'actions.runner.*' -and ([string]$_.PathName) -match $escapedInstallRoot
})
if ($services.Count -eq 0) { Fail 'runner_service_missing' }
if ($services.Count -ne 1) { Fail 'runner_service_ambiguous' }
$service = $services[0]
if ($service.State -ne 'Running') { Fail 'runner_service_not_running' }
$startName = [string]$service.StartName
if ([string]::IsNullOrWhiteSpace($startName)) { Fail 'runner_service_identity_missing' }

try {
    $account = New-Object Security.Principal.NTAccount($startName)
    $sid = $account.Translate([Security.Principal.SecurityIdentifier]).Value
} catch {
    Fail 'runner_service_identity_unresolvable'
}
if ($sid -notmatch '^S-1-') { Fail 'runner_service_sid_invalid' }

$grantArg = "*$($sid):(OI)(CI)M"
foreach ($path in @($RepoPath, $VaultRoot)) {
    & icacls.exe $path /grant:r $grantArg /T /Q | Out-Null
    if ($LASTEXITCODE -ne 0) { Fail 'acl_grant_failed' }
}

# Trust only the exact canonical Dominion repo path for Git ownership checks.
$gitSafePath = ($RepoPath -replace '\\','/').TrimEnd('/')
$existingSafe = @(& git config --system --get-all safe.directory 2>$null)
if ($LASTEXITCODE -ne 0 -and $LASTEXITCODE -ne 1) { Fail 'git_safe_directory_read_failed' }
if ($existingSafe -notcontains $gitSafePath) {
    & git config --system --add safe.directory $gitSafePath
    if ($LASTEXITCODE -ne 0) { Fail 'git_safe_directory_write_failed' }
}
$verifiedSafe = @(& git config --system --get-all safe.directory 2>$null)
if ($LASTEXITCODE -ne 0 -or $verifiedSafe -notcontains $gitSafePath) { Fail 'git_safe_directory_verify_failed' }

Write-Host "LAPTOP_RUNNER_ACL_REPAIR=PASS runner_service=$($service.Name) repo_acl=modify vault_acl=modify git_safe_directory=exact"
