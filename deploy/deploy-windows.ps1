# ============================================================================
# Kev Docker Desktop deploy script (PowerShell) — model chooser
# Run from anywhere:
#   .\deploy\deploy-windows.ps1                       # default: Kev-4B
#   .\deploy\deploy-windows.ps1 -Model 0.8B           # deploy Kev-0.8B instead
#   .\deploy\deploy-windows.ps1 -Model 4B -Run kev-4b-local -ApiKey <key>
#   .\deploy\deploy-windows.ps1 -Model 0.8B -Hub jaredpalmer/kev-0.8b -ApiKey <key>
# ============================================================================

param(
    [string]$Model = "4B",                   # which model: "4B" or "0.8B"
    [switch]$NoBuild,                        # skip the image build (use existing image)
    [string]$Run = "",                       # local checkpoint dir name under ./runs (default depends on -Model)
    [string]$ApiKey = "",                    # API key -> KEV_API_KEY (Bearer auth); falls back to $env:KEV_API_KEY
    [string]$Hub = ""                        # if set, deploy from a Hub id instead of the local run
)

$ErrorActionPreference = "Stop"

# ----- model-specific defaults -----
switch ($Model) {
    "4B"   { $ComposeName = "docker-compose-4B.yml";  $DefaultRun = "kev-4b-local";  $DefaultHub = "jaredpalmer/kev-4b";  $VramNote = "Kev-4B bf16 needs ~10-12 GB VRAM" }
    "0.8B" { $ComposeName = "docker-compose-0.8B.yml"; $DefaultRun = "kev-0.8b-local"; $DefaultHub = "jaredpalmer/kev-0.8b"; $VramNote = "Kev-0.8B bf16 needs only ~2-3 GB VRAM" }
    default { Write-Host "ERROR: -Model must be '4B' or '0.8B' (got '$Model')" -ForegroundColor Red; exit 1 }
}

# Resolve paths relative to this script so the cwd does not matter
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot  = Split-Path -Parent $ScriptDir
$Compose   = Join-Path $ScriptDir $ComposeName

Write-Host "==============================================" -ForegroundColor Cyan
Write-Host "Kev-$Model Windows Docker deploy" -ForegroundColor Cyan
Write-Host "==============================================" -ForegroundColor Cyan

# ===== 1. Preconditions =====
Write-Host "`n[1/6] Checking environment..." -ForegroundColor Yellow

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Host "ERROR: docker not found. Install Docker Desktop: https://www.docker.com/products/docker-desktop/" -ForegroundColor Red
    exit 1
}
Write-Host "OK Docker: $(docker --version)" -ForegroundColor Green

# PS5.1 + $ErrorActionPreference=Stop turns redirected native stderr (e.g. the
# DOCKER_INSECURE_NO_IPTABLES_RAW warning) into a terminating NativeCommandError,
# so do the redirect inside cmd instead.
cmd /c "docker info >nul 2>&1"
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Docker Desktop is not running. Start it first." -ForegroundColor Red
    exit 1
}
Write-Host "OK Docker daemon is up" -ForegroundColor Green

if (-not (Test-Path $Compose)) {
    Write-Host "ERROR: missing $Compose" -ForegroundColor Red
    exit 1
}
Write-Host "OK Compose file: $Compose" -ForegroundColor Green

if (Get-Command nvidia-smi -ErrorAction SilentlyContinue) {
    $gpuName = (nvidia-smi --query-gpu=name --format=csv,noheader | Select-Object -First 1)
    Write-Host "OK NVIDIA GPU: $gpuName ($VramNote)" -ForegroundColor Green
} else {
    Write-Host "WARN: no NVIDIA GPU visible — server will run on CPU (slow)" -ForegroundColor Yellow
}

# ===== 2. Build =====
Write-Host "`n[2/6] Building image..." -ForegroundColor Yellow

if (-not $NoBuild) {
    docker compose -f $Compose build
    if ($LASTEXITCODE -ne 0) { Write-Host "ERROR: image build failed" -ForegroundColor Red; exit 1 }
} else {
    Write-Host "Skipped (-NoBuild)" -ForegroundColor Cyan
}

# ===== 3. (Re)start =====
Write-Host "`n[3/6] Resolving model source, API key & starting service..." -ForegroundColor Yellow

# --- model source: local run (default) or Hub id ---
if (-not $Run) { $Run = $DefaultRun }
if ($Hub) {
    $env:KEV_RUN = $Hub
    Write-Host "Mode: Hub  -> KEV_RUN=$Hub" -ForegroundColor Cyan
} else {
    $LocalRunDir = Join-Path $ScriptDir "runs\$Run"
    if (-not (Test-Path $LocalRunDir -PathType Container)) {
        Write-Host "ERROR: local run directory not found: $LocalRunDir" -ForegroundColor Red
        Write-Host "       Place the checkpoint (base model + kev adapter, or a full checkpoint) there," -ForegroundColor Yellow
        Write-Host "       or deploy from a Hub id with:  .\deploy\deploy-windows.ps1 -Model $Model -Hub $DefaultHub" -ForegroundColor Yellow
        exit 1
    }
    # The checkpoint must contain at least head.pt (the pointer head); otherwise
    # kev.serve treats the path as a Hub id and fails obscurely at runtime.
    $HeadPt = Join-Path $LocalRunDir "head.pt"
    if (-not (Test-Path $HeadPt)) {
        Write-Host "ERROR: checkpoint 'head.pt' not found in $LocalRunDir" -ForegroundColor Red
        Write-Host "       Put the full Kev-$Model checkpoint there (head.pt + adapter_config.json" -ForegroundColor Yellow
        Write-Host "       + adapter_model.safetensors + tokenizer files), or deploy from a Hub id:" -ForegroundColor Yellow
        Write-Host "         .\deploy\deploy-windows.ps1 -Model $Model -Hub $DefaultHub" -ForegroundColor White
        exit 1
    }
    $env:KEV_RUN = "/kev/runs/$Run"
    Write-Host "Mode: local -> KEV_RUN=$env:KEV_RUN  (host: $LocalRunDir)" -ForegroundColor Cyan
}

# --- API key (Bearer auth) ---
if (-not $ApiKey) { $ApiKey = $env:KEV_API_KEY }
if ($ApiKey) {
    $env:KEV_API_KEY = $ApiKey
    Write-Host "API key: set (clients must send 'Authorization: Bearer <key>')" -ForegroundColor Green
} else {
    $env:KEV_API_KEY = ""
    Write-Host "API key: NONE -> server is OPEN (no auth). Set -ApiKey or `$env:KEV_API_KEY." -ForegroundColor Yellow
}

# ----- stop the other model's stack (both share container names `kev-server`/`kev-playground`) -----
$OtherModel = if ($Model -eq "4B") { "0.8B" } else { "4B" }
$OtherCompose = Join-Path $ScriptDir "docker-compose-$OtherModel.yml"
if (Test-Path $OtherCompose) {
    Write-Host "Stopping the other Kev-$OtherModel stack (if running) to free shared container names..." -ForegroundColor Cyan
    # `down` prints container status to stderr; under $ErrorActionPreference=Stop that
    # becomes a terminating NativeCommandError. Wrap in cmd /c and discard output.
    cmd /c "docker compose -f `"$OtherCompose`" down >nul 2>&1"
}

docker compose -f $Compose up -d
if ($LASTEXITCODE -ne 0) { Write-Host "ERROR: docker compose up failed" -ForegroundColor Red; exit 1 }

# ===== 4. Wait for readiness =====
$HealthHeaders = if ($ApiKey) { @{ Authorization = "Bearer $ApiKey" } } else { @{} }
Write-Host "`n[4/6] Waiting for http://localhost:8008/v1/models (auth=$(if ($ApiKey) { 'key' } else { 'open' }))..." -ForegroundColor Yellow

$maxWait = 600
$elapsed = 0
while ($elapsed -lt $maxWait) {
    Start-Sleep -Seconds 5
    try {
        $r = Invoke-WebRequest -Uri "http://localhost:8008/v1/models" -Method Get -TimeoutSec 5 -UseBasicParsing -Headers $HealthHeaders
        if ($r.StatusCode -eq 200) { break }
    } catch { }
    $elapsed += 5
    if ($elapsed % 30 -eq 0) { Write-Host "  waiting... ${elapsed}s" -ForegroundColor Cyan }
}

if ($elapsed -lt $maxWait) {
    Write-Host "OK Service is ready" -ForegroundColor Green
} else {
    Write-Host "WARN: not ready after ${maxWait}s — check logs:" -ForegroundColor Yellow
    Write-Host "      docker logs -f kev-server" -ForegroundColor Cyan
}

# ===== 4b. Wait for playground UI =====
Write-Host "`n[4b/6] Waiting for http://localhost:3000/ (playground UI)..." -ForegroundColor Yellow
$pWait = 120; $pElapsed = 0; $pReady = $false
while ($pElapsed -lt $pWait) {
    Start-Sleep -Seconds 3
    try {
        $pr = Invoke-WebRequest -Uri "http://localhost:3000/" -Method Get -TimeoutSec 5 -UseBasicParsing
        if ($pr.StatusCode -eq 200) { $pReady = $true; break }
    } catch { }
    $pElapsed += 3
}
if ($pReady) {
    Write-Host "OK Playground UI is ready" -ForegroundColor Green
} else {
    Write-Host "WARN: playground not ready after ${pWait}s — check: docker logs kev-playground" -ForegroundColor Yellow
}

# ===== 5. Status =====
Write-Host "`n[5/6] Status:" -ForegroundColor Yellow
docker compose -f $Compose ps

# ===== 6. Tips =====
Write-Host "`n==============================================" -ForegroundColor Cyan
Write-Host "Deploy done." -ForegroundColor Green
Write-Host "  API:           http://localhost:8008  (docs: /docs)" -ForegroundColor Green
Write-Host "  Playground UI: http://localhost:3000  (proxies /kev to kev-server)" -ForegroundColor Green
Write-Host "==============================================" -ForegroundColor Cyan

Write-Host "`nQuick start:" -ForegroundColor Yellow
Write-Host "  curl http://localhost:8008/v1/models" -ForegroundColor White
Write-Host "  open http://localhost:3000            # playground UI (kev / chess tabs)" -ForegroundColor White
Write-Host "  python scripts\test-api.py            # from the repo root" -ForegroundColor White
Write-Host "  docker logs -f kev-server" -ForegroundColor White
Write-Host "  docker logs -f kev-playground" -ForegroundColor White
Write-Host "  docker compose -f deploy\$ComposeName down" -ForegroundColor White

Write-Host "`nLocal run (default): put the checkpoint in .\deploy\runs\<name>\" -ForegroundColor Yellow
Write-Host "  .\deploy\deploy-windows.ps1 -Model $Model -Run $DefaultRun -ApiKey <your-key>" -ForegroundColor White
Write-Host "Hub run:" -ForegroundColor Yellow
Write-Host "  .\deploy\deploy-windows.ps1 -Model $Model -Hub $DefaultHub -ApiKey <your-key>" -ForegroundColor White
Write-Host "Switch models (stops the other stack first):" -ForegroundColor Yellow
Write-Host "  .\deploy\deploy-windows.ps1 -Model 0.8B" -ForegroundColor White
Write-Host "Change API key / checkpoint on a running stack:" -ForegroundColor Yellow
Write-Host "  `$env:KEV_API_KEY='<key>'; `$env:KEV_RUN='/kev/runs/$DefaultRun'; docker compose -f deploy\$ComposeName up -d" -ForegroundColor White

Write-Host "`nSee deploy\README.md for the full guide." -ForegroundColor Gray
