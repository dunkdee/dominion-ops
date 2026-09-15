$ErrorActionPreference = 'Stop'

$report = [ordered]@{
  audit = 'dominion_video_studio_windows_gpu_worker_readiness'
  timestamp_utc = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
  computer_name = $env:COMPUTERNAME
  os = (Get-CimInstance Win32_OperatingSystem).Caption
  cpu = (Get-CimInstance Win32_Processor | Select-Object -First 1 -ExpandProperty Name)
  logical_processors = (Get-CimInstance Win32_ComputerSystem).NumberOfLogicalProcessors
  memory_gib = [math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB, 2)
  nvidia_smi = $false
  cuda_visible = $false
  docker = $false
  paid_gpu_authorized = $false
  installation_performed = $false
  media_processed = $false
}

$nvidia = Get-Command nvidia-smi.exe -ErrorAction SilentlyContinue
if ($nvidia) {
  $report.nvidia_smi = $true
  $gpu = & $nvidia.Source --query-gpu=name,driver_version,memory.total,compute_cap --format=csv,noheader,nounits 2>$null
  $report.gpu = ($gpu -join '; ')
  $report.cuda_visible = $LASTEXITCODE -eq 0
}

$docker = Get-Command docker.exe -ErrorAction SilentlyContinue
if ($docker) {
  $report.docker = $true
  try { $report.docker_version = (& docker version --format '{{.Server.Version}}' 2>$null) } catch {}
}

$outDir = Join-Path $env:USERPROFILE 'dominion-video-studio'
New-Item -ItemType Directory -Force -Path $outDir | Out-Null
$outFile = Join-Path $outDir 'windows-gpu-worker-readiness.json'
$report | ConvertTo-Json -Depth 4 | Set-Content -Encoding UTF8 $outFile
Get-Content $outFile
Write-Host "`nSaved readiness report to: $outFile"
