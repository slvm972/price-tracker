# update_site.ps1 — обновить data.js для frontend Price Tracker
# Запуск из backend:
#   cd D:\1\price-tracker
#   .\update_site.ps1
#   .\update_site.ps1 -SkipScrape    # только make_viewer + copy
#   .\update_site.ps1 -Scrape        # полный online-сбор, затем export

param(
    [switch]$SkipScrape,
    [switch]$Scrape,
    [string]$InterfaceDir = "D:\1\interface",
    [int]$Limit = 50
)

$ErrorActionPreference = "Stop"
$BackendDir = $PSScriptRoot
if (-not $BackendDir) { $BackendDir = Get-Location }

Set-Location $BackendDir
Write-Host "=== Price Tracker: update site data ===" -ForegroundColor Cyan
Write-Host "Backend:  $BackendDir"
Write-Host "Interface: $InterfaceDir"
Write-Host ""

# 1) optional scrape
if ($Scrape -and -not $SkipScrape) {
    Write-Host "--- download_all.py --all --force-scrape --limit $Limit ---" -ForegroundColor Yellow
    python download_all.py --all --force-scrape --limit $Limit
    if ($LASTEXITCODE -ne 0) {
        Write-Host "download_all.py failed (exit $LASTEXITCODE). Abort." -ForegroundColor Red
        exit $LASTEXITCODE
    }
} elseif (-not $SkipScrape -and -not $Scrape) {
    Write-Host "(scrape skipped — use -Scrape for full online update)" -ForegroundColor DarkGray
}

# 2) export data.js
Write-Host "--- make_viewer.py ---" -ForegroundColor Yellow
python make_viewer.py
if ($LASTEXITCODE -ne 0) {
    Write-Host "make_viewer.py failed (exit $LASTEXITCODE). Abort." -ForegroundColor Red
    exit $LASTEXITCODE
}

$dataJs = Join-Path $BackendDir "data.js"
if (-not (Test-Path $dataJs)) {
    Write-Host "data.js not found after make_viewer. Abort." -ForegroundColor Red
    exit 1
}

# show CATALOG_UPDATED if present
$upd = Select-String -Path $dataJs -Pattern 'CATALOG_UPDATED\s*=\s*"([^"]+)"' | Select-Object -First 1
if ($upd) { Write-Host "CATALOG_UPDATED:" $upd.Matches.Groups[1].Value -ForegroundColor Green }

# 3) copy to frontend
if (-not (Test-Path $InterfaceDir)) {
    Write-Host "Interface dir not found: $InterfaceDir" -ForegroundColor Red
    Write-Host "Pass -InterfaceDir 'D:\path\to\interface'" -ForegroundColor Yellow
    exit 1
}

$dest = Join-Path $InterfaceDir "data.js"
Copy-Item -Path $dataJs -Destination $dest -Force
Write-Host "Copied data.js -> $dest" -ForegroundColor Green

Write-Host ""
Write-Host "=== Next (manual) ===" -ForegroundColor Cyan
Write-Host "cd $InterfaceDir"
Write-Host "git add data.js"
Write-Host 'git commit -m "data: update CATALOG"'
Write-Host "git push"
Write-Host ""
Write-Host "Site: https://slvm972.github.io/pricetracker-interface-found/price_viewer.html"
Write-Host "(wait 1-3 min, then Ctrl+F5)"
