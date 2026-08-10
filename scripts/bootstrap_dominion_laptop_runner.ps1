param(
    [string]$Repository = 'dunkdee/dominion-ops',
    [string]$InstallRoot = 'C:\actions-runner',
    [string]$RunnerName = 'dominion-laptop'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$RunnerVersion = '2.336.0'
$RunnerAsset = "actions-runner-win-x64-$RunnerVersion.zip"
$RunnerUrl = "https://github.com/actions/runner/releases/download/v$RunnerVersion/$RunnerAsset"
$RunnerSha256 = 'd59123a43003e357b0805b5d0f611d0bd2f65ab67d51bd070dd4e7a0f685c162'
$RepositoryUrl = "https://github.com/$Repository"

function Fail([string]$Reason) {
    Write-Host "LAPTOP_RUNNER_BOOTSTRAP=HOLD reason=$Reason"
    exit 1
}

function Is-Administrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]::new($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Get-DominionRunnerRecord {
    $runnerJson = & gh api "repos/$Repository/actions/runners" 2>$null
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($runnerJson)) {
        return $null
    }

    try {
        $payload = $runnerJson | ConvertFrom-Json -ErrorAction Stop
    } catch {
        return $null
    }

    return @($payload.runners | Where-Object { $_.name -eq $RunnerName } | Select-Object -First 1)
}

if (-not (Is-Administrator)) { Fail 'administrator_required' }
if (-not [Environment]::Is64BitOperatingSystem) { Fail 'windows_x64_required' }
if (-not (Get-Command git -ErrorAction SilentlyContinue)) { Fail 'git_missing' }
if (-not (Get-Command gh -ErrorAction SilentlyContinue)) { Fail 'github_cli_missing' }

& gh auth status --hostname github.com 1>$null 2>$null
if ($LASTEXITCODE -ne 0) { Fail 'github_cli_not_authenticated' }

# If an exact Dominion runner is already configured locally, do not overwrite it.
if (Test-Path -LiteralPath (Join-Path $InstallRoot '.runner')) {
    $services = @(Get-Service -ErrorAction SilentlyContinue | Where-Object { $_.Name -like 'actions.runner.*' })
    if ($services.Count -eq 0) { Fail 'existing_runner_config_without_service' }
    foreach ($service in $services) {
        if ($service.Status -ne 'Running') {
            Start-Service -Name $service.Name
        }
    }
    Start-Sleep -Seconds 3
    $runnerRecord = Get-DominionRunnerRecord
    if ($null -ne $runnerRecord -and $runnerRecord.status -eq 'online') {
        Write-Host "LAPTOP_RUNNER_BOOTSTRAP=PASS state=already_configured runner=$RunnerName service=running version=existing"
        exit 0
    }
    Fail 'existing_runner_not_online'
}

if (Test-Path -LiteralPath $InstallRoot) {
    $existing = @(Get-ChildItem -LiteralPath $InstallRoot -Force -ErrorAction Stop)
    if ($existing.Count -gt 0) { Fail 'install_root_not_empty' }
} else {
    New-Item -ItemType Directory -Path $InstallRoot -Force | Out-Null
}

$rootItem = Get-Item -LiteralPath $InstallRoot -Force
if (-not $rootItem.PSIsContainer -or ($rootItem.Attributes -band [IO.FileAttributes]::ReparsePoint)) { Fail 'install_root_not_safe_directory' }

$tempRoot = Join-Path $env:TEMP ("dominion-runner-bootstrap-" + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $tempRoot -Force | Out-Null
$zipPath = Join-Path $tempRoot $RunnerAsset
$registrationToken = $null

try {
    Invoke-WebRequest -UseBasicParsing -Uri $RunnerUrl -OutFile $zipPath
    $actualHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $zipPath).Hash.ToLowerInvariant()
    if ($actualHash -ne $RunnerSha256) { Fail 'runner_package_checksum_mismatch' }

    Expand-Archive -LiteralPath $zipPath -DestinationPath $InstallRoot -Force
    $config = Join-Path $InstallRoot 'config.cmd'
    if (-not (Test-Path -LiteralPath $config -PathType Leaf)) { Fail 'runner_config_missing_after_extract' }

    # GitHub's registration token is time-limited. Keep it only in process memory and never print it.
    $tokenJson = & gh api -X POST "repos/$Repository/actions/runners/registration-token" 2>$null
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($tokenJson)) { Fail 'github_admin_runner_token_unavailable' }
    try {
        $tokenPayload = $tokenJson | ConvertFrom-Json -ErrorAction Stop
        $registrationToken = [string]$tokenPayload.token
    } catch {
        Fail 'github_admin_runner_token_invalid_response'
    }
    if ([string]::IsNullOrWhiteSpace($registrationToken)) { Fail 'github_admin_runner_token_unavailable' }

    Push-Location $InstallRoot
    try {
        & .\config.cmd `
            --unattended `
            --replace `
            --url $RepositoryUrl `
            --token $registrationToken.Trim() `
            --name $RunnerName `
            --work '_work' `
            --runasservice
        if ($LASTEXITCODE -ne 0) { Fail 'runner_configuration_failed' }
    } finally {
        Pop-Location
    }
    $registrationToken = $null

    $services = @(Get-Service -ErrorAction SilentlyContinue | Where-Object { $_.Name -like 'actions.runner.*' })
    if ($services.Count -eq 0) { Fail 'runner_service_missing' }
    foreach ($service in $services) {
        if ($service.Status -ne 'Running') {
            Start-Service -Name $service.Name
        }
    }

    $online = $false
    for ($attempt = 0; $attempt -lt 20; $attempt++) {
        Start-Sleep -Seconds 3
        $runnerRecord = Get-DominionRunnerRecord
        if ($null -ne $runnerRecord -and $runnerRecord.status -eq 'online') {
            $online = $true
            break
        }
    }
    if (-not $online) { Fail 'runner_registered_but_not_online' }

    Write-Host "LAPTOP_RUNNER_BOOTSTRAP=PASS state=online runner=$RunnerName service=running version=$RunnerVersion"
} finally {
    $registrationToken = $null
    if (Test-Path -LiteralPath $tempRoot) {
        Remove-Item -LiteralPath $tempRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}
