$ErrorActionPreference = 'Continue'

Write-Host '=== BUDDY WINDOWS NODE PREFLIGHT ==='
Write-Host ('UTC ' + [DateTime]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ssZ'))
Write-Host ('Computer: ' + $env:COMPUTERNAME)
Write-Host ('User: ' + $env:USERNAME)
Write-Host ('Windows: ' + [Environment]::OSVersion.VersionString)

$homeDir = $env:USERPROFILE
$repoCandidates = @(
    (Join-Path $homeDir 'dominion-ops'),
    'C:\Users\Dell\dominion-ops'
) | Select-Object -Unique

$buddyCandidates = @(
    (Join-Path $homeDir 'buddy_core'),
    (Join-Path $homeDir 'dominion-ops\buddy_core'),
    'C:\Users\Dell\buddy_core',
    'C:\Users\Dell\dominion-ops\buddy_core'
) | Select-Object -Unique

Write-Host '=== CANDIDATE PATHS ==='
$repo = $null
foreach ($p in $repoCandidates) {
    if (Test-Path $p) {
        Write-Host "REPO_FOUND $p"
        if (-not $repo) { $repo = $p }
    } else {
        Write-Host "REPO_MISSING $p"
    }
}

$buddyDirs = @()
foreach ($p in $buddyCandidates) {
    if (Test-Path $p) {
        Write-Host "BUDDY_FOUND $p"
        $buddyDirs += $p
    } else {
        Write-Host "BUDDY_MISSING $p"
    }
}

Write-Host '=== PYTHON ==='
try { python --version } catch { Write-Host 'python not found' }
try { py --version } catch { Write-Host 'py launcher not found' }

Write-Host '=== GIT ==='
try { git --version } catch { Write-Host 'git not found' }
if ($repo) {
    Push-Location $repo
    try {
        Write-Host ('Repo root: ' + (git rev-parse --show-toplevel))
        Write-Host ('Branch: ' + (git branch --show-current))
        Write-Host ('HEAD: ' + (git rev-parse HEAD))
        Write-Host 'Status:'
        git status --short --untracked-files=all | Select-Object -First 200
        Write-Host 'Tracked Buddy-related paths:'
        git ls-files | Select-String -Pattern 'buddy|jarvis|sentinel|proposal|brain|ollama' | Select-Object -First 250
    } catch {
        Write-Host ('Git inspection failed: ' + $_.Exception.Message)
    }
    Pop-Location
}

Write-Host '=== OLLAMA / LOCAL BRAIN ==='
try {
    $ollama = Get-Command ollama -ErrorAction Stop
    Write-Host ('Ollama: ' + $ollama.Source)
    ollama list
} catch {
    Write-Host 'OLLAMA_NOT_FOUND'
}

Write-Host '=== BUDDY FILE INVENTORY / HASHES ==='
foreach ($b in $buddyDirs) {
    Write-Host "--- $b"
    Get-ChildItem -Path $b -File -Recurse -ErrorAction SilentlyContinue |
        Where-Object { $_.Extension -in '.py','.json','.md','.yaml','.yml','.ps1' } |
        Select-Object -First 250 -ExpandProperty FullName

    $highValue = @(
        (Join-Path $b 'buddy_web.py'),
        (Join-Path $b 'buddy_bridge_api.py'),
        (Join-Path $b 'sentinel.py'),
        (Join-Path $b 'proposal_queue.py'),
        (Join-Path $b 'port_manifest.json'),
        (Join-Path $b 'core\brain.py'),
        (Join-Path $b 'core\router.py'),
        (Join-Path $b 'core\planner.py'),
        (Join-Path $b 'core\local_model.py'),
        (Join-Path $b 'phi_memory.py'),
        (Join-Path $b 'jarvis\jarvis_core.py')
    )
    foreach ($f in $highValue) {
        if (Test-Path $f) {
            try {
                $h = Get-FileHash -Algorithm SHA256 -Path $f
                Write-Host ("SHA256 {0} {1}" -f $h.Hash, $f)
            } catch { Write-Host "HASH_FAIL $f" }
        }
    }
}

Write-Host '=== BUDDY / AI PROCESSES ==='
Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Where-Object {
        $_.Name -match 'python|ollama|node' -or
        $_.CommandLine -match 'buddy|jarvis|ollama|dominion'
    } |
    Select-Object ProcessId, Name, CommandLine |
    Format-Table -AutoSize -Wrap

Write-Host '=== LISTENING PORTS ==='
$ports = 5052,5055,5056,5070,5060,5678,9380,11434
foreach ($p in $ports) {
    $listeners = Get-NetTCPConnection -State Listen -LocalPort $p -ErrorAction SilentlyContinue
    if ($listeners) {
        foreach ($l in $listeners) {
            Write-Host ("LISTEN {0}:{1} PID={2}" -f $l.LocalAddress,$l.LocalPort,$l.OwningProcess)
        }
    }
}

Write-Host '=== WINDOWS SERVICES / SCHEDULED TASKS ==='
Get-Service -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -match 'buddy|ollama|dominion|jarvis' -or $_.DisplayName -match 'buddy|ollama|dominion|jarvis' } |
    Select-Object Status, Name, DisplayName |
    Format-Table -AutoSize

Get-ScheduledTask -ErrorAction SilentlyContinue |
    Where-Object { $_.TaskName -match 'buddy|ollama|dominion|jarvis' -or $_.TaskPath -match 'buddy|ollama|dominion|jarvis' } |
    Select-Object TaskName, TaskPath, State |
    Format-Table -AutoSize

Write-Host '=== ENV VAR NAMES ONLY ==='
Get-ChildItem Env: |
    Where-Object { $_.Name -match '^(BUDDY|OLLAMA|OPENAI|ANTHROPIC|GROQ|GEMINI|GOOGLE|N8N|CONDUCTOR|TELEGRAM)' } |
    Sort-Object Name |
    ForEach-Object { Write-Host ($_.Name + '=<REDACTED>') }

Write-Host '=== NODE READINESS SUMMARY ==='
if ($buddyDirs.Count -eq 0) { Write-Host 'FAIL: no Buddy runtime directory found in expected laptop locations' }
else { Write-Host ('Buddy runtime candidates: ' + $buddyDirs.Count) }
if (Get-Command ollama -ErrorAction SilentlyContinue) { Write-Host 'Local brain runtime: AVAILABLE (Ollama)' }
else { Write-Host 'Local brain runtime: NOT DETECTED' }
Write-Host '=== PREFLIGHT COMPLETE: NO MUTATIONS PERFORMED ==='
