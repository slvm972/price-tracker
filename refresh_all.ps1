#requires -Version 7.0
<#
.SYNOPSIS
  Надёжное поочередное обновление цен всех сетей Price Tracker.

.DESCRIPTION
  Запускает download_all.py отдельным процессом на каждую сеть,
  пишет UTF-8 журналы, повторяет при временных сбоях, не даёт ПК уснуть,
  в конце печатает таблицу свежести данных. Опционально -Build → data.js.

  Ветка: feat/refresh-script (не вливать в master без проверки).
  Не делает git commit / git push.

.EXAMPLE
  cd D:\1\price-tracker
  Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
  .\refresh_all.ps1 -Only "GoodPharm,SalachDabach"

.EXAMPLE
  .\refresh_all.ps1 -Only GoodPharm -Build
#>

param(
    [string]$Only = "",
    [switch]$Build,
    [string]$InterfaceDir = "D:\1\interface",
    [int]$Limit = 50,
    [int]$TimeoutMinutes = 45,
    [int]$MaxAttempts = 3,
    [int]$RetryDelaySec = 90,
    [int]$StaleDays = 3
)

$ErrorActionPreference = "Continue"
$BackendDir = if ($PSScriptRoot) { $PSScriptRoot } else { (Get-Location).Path }
Set-Location $BackendDir

# ── 31 сеть (имена классов / --chains) ───────────────────────────
$AllChains = @(
    "Bareket",
    "CityMarketShops",
    "DorAlon",
    "FreshMarketAndSuperDosh",
    "GoodPharm",
    "HaziHinam",
    "HetCohenNewSource",
    "Keshet",
    "KingStore",
    "Maayan2000",
    "MahsaniAShukNewSource",
    "MeshnatYosef1",
    "MeshnatYosef2",
    "Osherad",
    "Polizer",
    "RamiLevy",
    "SalachDabach",
    "ShefaBarcartAshem",
    "Shufersal",
    "ShukAhir",
    "StopMarket",
    "SuperPharm",
    "SuperSapir",
    "SuperYuda",
    "TivTaam",
    "VictoryNewSource",
    "Wolt",
    "YaynotBitanAndCarrefour",
    "Yellow",
    "Yohananof",
    "ZolVeBegadol"
)

$env:PYTHONIOENCODING = "utf-8"
$Python = "python"
$LockPath = Join-Path $BackendDir "refresh.lock"
$DayStamp = Get-Date -Format "yyyyMMdd"
$LogDir = Join-Path $BackendDir "logs" $DayStamp
$DbPath = Join-Path $BackendDir "prices.db"

# ── Helpers ──────────────────────────────────────────────────────

function Write-Info([string]$msg) { Write-Host $msg -ForegroundColor Cyan }
function Write-Ok([string]$msg)   { Write-Host $msg -ForegroundColor Green }
function Write-Warn([string]$msg) { Write-Host $msg -ForegroundColor Yellow }
function Write-Err([string]$msg)  { Write-Host $msg -ForegroundColor Red }

function Get-ChainList {
    if ([string]::IsNullOrWhiteSpace($Only)) { return $AllChains }
    $wanted = $Only.Split(",") | ForEach-Object { $_.Trim() } | Where-Object { $_ }
    $out = [System.Collections.Generic.List[string]]::new()
    foreach ($name in $wanted) {
        $hit = $AllChains | Where-Object { $_ -ieq $name } | Select-Object -First 1
        if ($hit) { $out.Add($hit) }
        else { Write-Warn "Неизвестная сеть (пропуск): $name" }
    }
    return $out
}

function Enter-Lock {
    if (Test-Path $LockPath) {
        $old = Get-Content $LockPath -ErrorAction SilentlyContinue
        Write-Err "Уже запущен другой refresh (lock: $LockPath)."
        if ($old) { Write-Err "  $old" }
        Write-Err "Если процесс точно мёртв — удалите refresh.lock и повторите."
        exit 2
    }
    @(
        "pid=$PID"
        "started=$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
        "host=$env:COMPUTERNAME"
    ) | Set-Content -Path $LockPath -Encoding utf8
}

function Exit-Lock {
    if (Test-Path $LockPath) { Remove-Item $LockPath -Force -ErrorAction SilentlyContinue }
}

function Enable-NoSleep {
    # ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_AWAYMODE_REQUIRED
    Add-Type -Namespace Win32 -Name Power -ErrorAction SilentlyContinue -MemberDefinition @"
[System.Runtime.InteropServices.DllImport("kernel32.dll")]
public static extern uint SetThreadExecutionState(uint esFlags);
"@
    if (-not ("Win32.Power" -as [type])) { return $false }
    $ES_CONTINUOUS = [uint32]"0x80000000"
    $ES_SYSTEM_REQUIRED = [uint32]"0x00000001"
    $ES_AWAYMODE_REQUIRED = [uint32]"0x00000040"
    [void][Win32.Power]::SetThreadExecutionState($ES_CONTINUOUS -bor $ES_SYSTEM_REQUIRED -bor $ES_AWAYMODE_REQUIRED)
    return $true
}

function Disable-NoSleep {
    if (-not ("Win32.Power" -as [type])) { return }
    $ES_CONTINUOUS = [uint32]"0x80000000"
    [void][Win32.Power]::SetThreadExecutionState($ES_CONTINUOUS)
}

function Backup-PricesDb {
    if (-not (Test-Path $DbPath)) {
        Write-Warn "prices.db не найден — резервная копия пропущена."
        return
    }
    $bak = Join-Path $BackendDir ("prices.db.bak_" + $DayStamp)
    if (-not (Test-Path $bak)) {
        Copy-Item $DbPath $bak -Force
        Write-Ok "Резерв: $bak"
    } else {
        Write-Info "Резерв за сегодня уже есть: $bak"
    }
    # держать последние 3 bak_YYYYMMDD
    $baks = Get-ChildItem $BackendDir -Filter "prices.db.bak_*" -File |
        Sort-Object Name -Descending
    if ($baks.Count -gt 3) {
        $baks | Select-Object -Skip 3 | ForEach-Object {
            Remove-Item $_.FullName -Force
            Write-Info "Удалён старый резерв: $($_.Name)"
        }
    }
}

function Get-ResultFromLog([string]$logPath) {
    # Returns hashtable: Status (OK|FAIL|MISSING), Saved (int|null), Downloaded, Errors, Raw
    $out = @{ Status = "MISSING"; Saved = $null; Downloaded = $null; Errors = $null; Raw = $null }
    if (-not (Test-Path $logPath)) { return $out }
    $lines = Get-Content $logPath -Encoding utf8 -ErrorAction SilentlyContinue
    if (-not $lines) { $lines = Get-Content $logPath -ErrorAction SilentlyContinue }
    if (-not $lines) { return $out }
    # last RESULT line wins
    for ($i = $lines.Count - 1; $i -ge 0; $i--) {
        $line = $lines[$i]
        if ($line -match 'RESULT\s+chain=(\S+)\s+status=(OK|FAIL)\s+downloaded=(\d+)\s+saved=(\d+)\s+errors=(\d+)') {
            $out.Status = $Matches[2]
            $out.Downloaded = [int]$Matches[3]
            $out.Saved = [int]$Matches[4]
            $out.Errors = [int]$Matches[5]
            $out.Raw = $line.Trim()
            return $out
        }
    }
    return $out
}

function Test-LogFailure {
    param(
        [string]$logPath,
        [int]$ExitCode = -1
    )
    # Success ONLY when RESULT status=OK is present.
    # download_all.py: exit 0 = all OK, exit 3 = at least one FAIL.
    if (-not (Test-Path $logPath)) { return $true }
    $raw = Get-Content $logPath -Raw -Encoding utf8 -ErrorAction SilentlyContinue
    if (-not $raw) { $raw = Get-Content $logPath -Raw -ErrorAction SilentlyContinue }
    if ($raw -match "TIMEOUT after") { return $true }

    $res = Get-ResultFromLog $logPath
    if ($res.Status -eq "OK") { return $false }
    if ($res.Status -eq "FAIL") { return $true }

    # No RESULT line → fail (do not trust exit 0 alone without RESULT)
    if ($ExitCode -eq 3) { return $true }
    if ($ExitCode -ne 0) { return $true }
    return $true
}

function Get-SavedCountFromLog([string]$logPath) {
    $res = Get-ResultFromLog $logPath
    if ($null -ne $res.Saved) { return [int]$res.Saved }
    return $null
}

function Invoke-ChainOnce {
    param(
        [string]$Chain,
        [string]$LogPath,
        [int]$Attempt
    )
    $argList = @(
        "-u", "download_all.py",
        "--chains", $Chain,
        "--force-scrape",
        "--limit", "$Limit"
    )
    Write-Info "[$Chain] попытка $Attempt/$MaxAttempts → $LogPath"

    $stdoutLog = "$LogPath.stdout.tmp"
    $stderrLog = "$LogPath.stderr.tmp"
    Remove-Item $stdoutLog, $stderrLog -Force -ErrorAction SilentlyContinue

    $env:PYTHONIOENCODING = "utf-8"
    $env:PYTHONUTF8 = "1"

    $proc = Start-Process -FilePath $Python `
        -ArgumentList $argList `
        -WorkingDirectory $BackendDir `
        -RedirectStandardOutput $stdoutLog `
        -RedirectStandardError $stderrLog `
        -NoNewWindow `
        -PassThru

    $timeoutMs = [Math]::Max(1, $TimeoutMinutes) * 60 * 1000
    $finished = $proc.WaitForExit($timeoutMs)
    if (-not $finished) {
        Write-Warn "[$Chain] таймаут ${TimeoutMinutes} мин — завершаем PID $($proc.Id)"
        try { $proc.Kill($true) } catch {
            try { Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue } catch {}
        }
        Start-Sleep -Seconds 2
        "TIMEOUT after ${TimeoutMinutes} minutes" | Set-Content -Path $LogPath -Encoding utf8
        if (Test-Path $stdoutLog) { Get-Content $stdoutLog -Raw -ErrorAction SilentlyContinue | Add-Content $LogPath -Encoding utf8 }
        if (Test-Path $stderrLog) { Get-Content $stderrLog -Raw -ErrorAction SilentlyContinue | Add-Content $LogPath -Encoding utf8 }
        Remove-Item $stdoutLog, $stderrLog -Force -ErrorAction SilentlyContinue
        return $false
    }

    $exitCode = $proc.ExitCode
    if ($null -eq $exitCode) { $exitCode = -1 }

    # объединить stdout+stderr (пробуем utf8, иначе default)
    $parts = [System.Collections.Generic.List[string]]::new()
    foreach ($f in @($stdoutLog, $stderrLog)) {
        if (-not (Test-Path $f)) { continue }
        $chunk = Get-Content $f -Raw -Encoding utf8 -ErrorAction SilentlyContinue
        if ([string]::IsNullOrEmpty($chunk)) {
            $chunk = Get-Content $f -Raw -ErrorAction SilentlyContinue
        }
        if ($chunk) { [void]$parts.Add($chunk) }
    }
    ($parts -join "`n") | Set-Content -Path $LogPath -Encoding utf8
    Remove-Item $stdoutLog, $stderrLog -Force -ErrorAction SilentlyContinue

    $res = Get-ResultFromLog $LogPath
    if (Test-LogFailure -logPath $LogPath -ExitCode ([int]$exitCode)) {
        $extra = if ($res.Raw) { " | $($res.Raw)" } else { "" }
        Write-Warn "[$Chain] FAIL (exit $exitCode)$extra"
        return $false
    }
    $extra = if ($res.Raw) { " | $($res.Raw)" } else { "" }
    Write-Ok "[$Chain] OK (exit $exitCode)$extra"
    return $true
}

function Invoke-ChainWithRetries {
    param([string]$Chain)
    New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
    $ok = $false
    $attempts = 0
    $lastLog = $null
    for ($a = 1; $a -le $MaxAttempts; $a++) {
        $attempts = $a
        $lastLog = Join-Path $LogDir ("load_{0}_try{1}.log" -f $Chain, $a)
        # основной путь без _try для последней/успешной
        $mainLog = Join-Path $LogDir ("load_{0}.log" -f $Chain)
        $success = Invoke-ChainOnce -Chain $Chain -LogPath $lastLog -Attempt $a
        # всегда копируем последнюю попытку в load_<Сеть>.log
        if (Test-Path $lastLog) { Copy-Item $lastLog $mainLog -Force }
        if ($success) {
            $ok = $true
            break
        }
        if ($a -lt $MaxAttempts) {
            Write-Warn "[$Chain] пауза ${RetryDelaySec}с перед повтором..."
            Start-Sleep -Seconds $RetryDelaySec
        }
    }
    $saved = Get-SavedCountFromLog (Join-Path $LogDir ("load_{0}.log" -f $Chain))
    return [pscustomobject]@{
        Chain    = $Chain
        Attempts = $attempts
        Ok       = $ok
        Saved    = $saved
        Log      = (Join-Path $LogDir ("load_{0}.log" -f $Chain))
    }
}

function Get-RetailerLastUpdates {
    # только чтение prices.db
    if (-not (Test-Path $DbPath)) { return @{} }
    $py = @'
import sqlite3, sys
db = sys.argv[1]
con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
cur = con.cursor()
try:
    rows = cur.execute("""
        SELECT s.retailer, MAX(p.recorded_at)
        FROM prices p
        JOIN stores s ON s.id = p.store_id
        GROUP BY s.retailer
    """).fetchall()
except Exception as e:
    print("ERR", e, file=sys.stderr)
    rows = []
for r, ts in rows:
    print(f"{r}\t{ts or ''}")
'@
    $tmp = Join-Path $env:TEMP ("pt_lastupd_{0}.py" -f $PID)
    Set-Content -Path $tmp -Value $py -Encoding utf8
    $map = @{}
    try {
        $out = & $Python $tmp $DbPath 2>$null
        foreach ($line in $out) {
            if ($line -match "^([^\t]+)\t(.*)$") {
                $map[$Matches[1]] = $Matches[2].Trim()
            }
        }
    } finally {
        Remove-Item $tmp -Force -ErrorAction SilentlyContinue
    }
    return $map
}

function Test-IsStale([string]$ts, [int]$days) {
    if ([string]::IsNullOrWhiteSpace($ts)) { return $true }
    $s = $ts.Trim().Replace("T", " ")
    if ($s.Length -gt 19) { $s = $s.Substring(0, 19) }
    try {
        $dt = [datetime]::ParseExact($s, "yyyy-MM-dd HH:mm:ss", [System.Globalization.CultureInfo]::InvariantCulture)
    } catch {
        try { $dt = [datetime]::Parse($ts) } catch { return $true }
    }
    return ((Get-Date) - $dt).TotalDays -gt $days
}

function Invoke-Build {
    Write-Info "=== -Build: make_viewer + copy data.js ==="
    # Текущий make_viewer.py может не знать --min-chains; пробуем, иначе без флага.
    & $Python make_viewer.py --min-chains 2
    if ($LASTEXITCODE -ne 0) {
        Write-Warn "make_viewer.py --min-chains 2 не принят (код $LASTEXITCODE) — повтор без флага"
        & $Python make_viewer.py
        if ($LASTEXITCODE -ne 0) {
            Write-Err "make_viewer.py завершился с ошибкой $LASTEXITCODE"
            return $false
        }
    }
    $src = Join-Path $BackendDir "data.js"
    if (-not (Test-Path $src)) {
        Write-Err "data.js не создан"
        return $false
    }
    if (-not (Test-Path $InterfaceDir)) {
        Write-Err "Нет каталога интерфейса: $InterfaceDir"
        return $false
    }
    $dst = Join-Path $InterfaceDir "data.js"
    Copy-Item $src $dst -Force
    Write-Ok "Скопировано: $src → $dst"
    $len = (Get-Item $dst).Length
    Write-Ok ("data.js размер: {0:N0} байт" -f $len)
    Write-Host ""
    Write-Info "=== Публикация вручную (git) ==="
    Write-Host "cd $InterfaceDir"
    Write-Host "git add data.js"
    Write-Host 'git commit -m "data: update CATALOG"'
    Write-Host "git push"
    Write-Host "Site: https://slvm972.github.io/pricetracker-interface-found/price_viewer.html"
    Write-Host "(подождите 1–3 мин, затем Ctrl+F5)"
    return $true
}

# ── Main ─────────────────────────────────────────────────────────

$chains = @(Get-ChainList)
if ($chains.Count -eq 0) {
    Write-Err "Список сетей пуст."
    exit 1
}

Enter-Lock
$noSleep = $false
$results = @()
$exitCode = 0

try {
    Write-Info "=== Price Tracker refresh_all ==="
    Write-Host "Backend:  $BackendDir"
    Write-Host "Logs:     $LogDir"
    Write-Host "Chains:   $($chains -join ', ')"
    Write-Host "Limit:    $Limit | Timeout: ${TimeoutMinutes}m | Retries: $MaxAttempts"
    Write-Host ""

    $noSleep = Enable-NoSleep
    if ($noSleep) { Write-Info "Режим «не спать» включён (SetThreadExecutionState)." }

    Backup-PricesDb

    foreach ($ch in $chains) {
        Write-Host ""
        Write-Info "──────── $ch ────────"
        $results += Invoke-ChainWithRetries -Chain $ch
    }

    Write-Host ""
    Write-Info "=== Сводка ==="
    $lastMap = Get-RetailerLastUpdates
    $staleList = [System.Collections.Generic.List[string]]::new()

    $fmt = "{0,-28} {1,8} {2,12} {3,-20} {4}"
    Write-Host ($fmt -f "Сеть", "Попыток", "Записей+", "Последние данные", "Статус")
    Write-Host ("-" * 85)

    foreach ($r in $results) {
        $ts = $null
        # точное имя retailer в БД часто = имя класса
        if ($lastMap.ContainsKey($r.Chain)) { $ts = $lastMap[$r.Chain] }
        else {
            $key = $lastMap.Keys | Where-Object { $_ -ieq $r.Chain } | Select-Object -First 1
            if ($key) { $ts = $lastMap[$key] }
        }
        $stale = Test-IsStale -ts $ts -days $StaleDays
        $status = if (-not $r.Ok) { "СБОЙ" }
                  elseif ($stale) { "УСТАРЕЛА" }
                  else { "OK" }
        if ($stale -or -not $r.Ok) { $staleList.Add($r.Chain) | Out-Null }
        $savedStr = if ($null -eq $r.Saved) { "—" } else { "$($r.Saved)" }
        $tsStr = if ($ts) { $ts } else { "—" }
        $line = $fmt -f $r.Chain, $r.Attempts, $savedStr, $tsStr, $status
        if ($status -eq "OK") { Write-Host $line -ForegroundColor Green }
        elseif ($status -eq "УСТАРЕЛА") { Write-Host $line -ForegroundColor Yellow }
        else { Write-Host $line -ForegroundColor Red }
    }

    if ($staleList.Count -gt 0) {
        Write-Warn ("Устаревшие / сбой: " + ($staleList -join ", "))
        $exitCode = 1
    } else {
        Write-Ok "Все выбранные сети свежие (≤ $StaleDays дн.)."
    }

    if ($Build) {
        Write-Host ""
        $buildOk = Invoke-Build
        if (-not $buildOk) { $exitCode = 1 }
    }
}
finally {
    if ($noSleep) {
        Disable-NoSleep
        Write-Info "Режим «не спать» снят."
    }
    Exit-Lock
}

exit $exitCode
