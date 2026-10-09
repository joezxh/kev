# One-click deploy for the Kev stack (kev-server + kev-playground).
# Builds both images and starts the two containers.
param(
    [string]$Compose = "$PSScriptRoot/docker-compose.yml"
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "Building and starting Kev stack (kev-server + kev-playground)..." -ForegroundColor Cyan
docker compose -f $Compose up -d --build

Write-Host "`nStack is up:" -ForegroundColor Green
Write-Host "  Playground:  http://localhost:3030" -ForegroundColor White
Write-Host "  Server API:  http://localhost:8008  (docs: /docs)" -ForegroundColor White
Write-Host "  Console API: http://localhost:8008/console/api" -ForegroundColor White
Write-Host "`nStop it with:  docker compose -f $Compose down" -ForegroundColor Yellow
