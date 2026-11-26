<#
.SYNOPSIS
  Обновление «капризных» сетей с домашнего ПК и подготовка пакета для облака.

.DESCRIPTION
  1) запускает refresh_all.ps1 только для шести сетей, которые облако собрать не может;
  2) отбирает свежие файлы этих сетей (по умолчанию не старше 3 дней),
     переименовывает папки под облачные названия и упаковывает всё в D:\1\upload\home-dumps.zip;
  3) загружает пакет в релиз db-latest автоматически (режим upload)
     или подсказывает, как это сделать вручную.
  Облако само примет пакет при ближайшем запуске и удалит его из релиза.

  РЕЖИМЫ (для запуска планировщиком с ключом -Auto режим берётся из файла
  D:\1\upload\home_mode.txt, в нём одно слово):
    manual  - при -Auto ничего не делать (при обычном запуске без -Auto: как раньше,
              скачать, упаковать, показать инструкцию и открыть папку с файлом);
    pack    - скачать и упаковать, затем открыть папку с готовым пакетом
              (в релиз вы загружаете вручную);
    upload  - скачать, упаковать и загрузить пакет в релиз сам
              (нужен токен GitHub, сохранённый на этом ПК; вне окна 21:00-22:10).
  Ключ -Mode manual|pack|upload задаёт режим явно и перекрывает файл.

.EXAMPLE
  # как раньше: ручной запуск
  pwsh -NoProfile -ExecutionPolicy Bypass -File D:\1\price-tracker\home_update.ps1

.EXAMPLE
  # только упаковать то, что уже скачано (без нового скачивания)
  pwsh -NoProfile -ExecutionPolicy Bypass -File D:\1\price-tracker\home_update.ps1 -PackOnly

.EXAMPLE
  # если файл получился больше 1,9 ГБ - взять только файлы за последний день
  pwsh -NoProfile -ExecutionPolicy Bypass -File D:\1\price-tracker\home_update.ps1 -PackOnly -MaxAgeDays 1

.EXAMPLE
  # запуск планировщиком: без окон, режим из файла home_mode.txt, журнал в D:\1\upload\logs
  pwsh -NoProfile -ExecutionPolicy Bypass -File D:\1\price-tracker\home_update.ps1 -Auto
#>

param(
    [switch]$PackOnly,
    [int]$MaxAgeDays = 3,
    [switch]$Auto,
    [ValidateSet("manual", "pack", "upload")]
    [string]$Mode
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"

$Backend    = "D:\1\price-tracker"
$Upload     = "D:\1\upload"
$Stage      = Join-Path $Upload "home-dumps-stage"
$Zip        = Join-Path $Upload "home-dumps.zip"
$ModeFile   = Join-Path $Upload "home_mode.txt"
$LogDir     = Join-Path $Upload "logs"
$TokenFile  = Join-Path $env:USERPROFILE ".price-tracker\github-token.xml"
$Repo       = "slvm972/price-tracker"
$Tag        = "db-latest"
$ReleaseUrl = "https://github.com/$Repo/releases/tag/$Tag"

# Сети, которые облако собрать не может (имена как в refresh_all.ps1)
$Chains = "HaziHinam,SuperPharm,YaynotBitanAndCarrefour,HetCohenNewSource,MahsaniAShukNewSource,VictoryNewSource"

# Папки в dumps: имя в облаке = список возможных имён дома
$Map = [ordered]@{
    "HAZIHINAM"               = @("HaziHinam", "HAZIHINAM")
    "SuperPharm"              = @("SuperPharm")
    "YaynotBitanAndCarrefour" = @("YaynotBitanAndCarrefour")
    "HetCohen"                = @("HetCohenNewSource", "HetCohen")
    "MahsaniAShuk"            = @("MahsaniAShukNewSource", "MahsaniAShuk")
    "VictoryNewSource"        = @("Victory", "VictoryNewSource")
}

function Say {
    param(
        [string]$Text,
        [string]$Color = "Cyan"
    )
    Write-Host $Text -ForegroundColor $Color
}

# Окно вечернего облачного запуска (21:30): в это время пакет не загружаем
function Test-CloudWindow {
    $t = Get-Date
    $minutes = $t.Hour * 60 + $t.Minute
    return ($minutes -ge (21 * 60) -and $minutes -le (22 * 60 + 10))
}

function Get-GitHubToken {
    if (-not (Test-Path $TokenFile)) { return $null }
    try {
        $sec = Import-Clixml -Path $TokenFile
        $cred = New-Object System.Net.NetworkCredential("", $sec)
        return $cred.Password
    }
    catch {
        return $null
    }
}

# Загрузка пакета в релиз через API GitHub. Возвращает $true при успехе.
function Send-ToRelease {
    param([string]$ZipPath)
    $token = Get-GitHubToken
    if (-not $token) {
        Say "Токен GitHub не найден ($TokenFile): автозагрузка невозможна." "Yellow"
        return $false
    }
    $headers = @{
        Authorization = "Bearer $token"
        Accept        = "application/vnd.github+json"
    }
    try {
        $rel = Invoke-RestMethod -Uri "https://api.github.com/repos/$Repo/releases/tags/$Tag" -Headers $headers -TimeoutSec 60
        foreach ($a in @($rel.assets | Where-Object { $_.name -eq "home-dumps.zip" })) {
            Say "В релизе уже лежит home-dumps.zip (облако его ещё не приняло): заменяем свежим." "Yellow"
            Invoke-RestMethod -Method Delete -Uri "https://api.github.com/repos/$Repo/releases/assets/$($a.id)" -Headers $headers -TimeoutSec 60 | Out-Null
        }
        $size = (Get-Item $ZipPath).Length
        Say "Загружаем пакет в релиз (может занять несколько минут)..."
        $up = Invoke-RestMethod -Method Post `
            -Uri "https://uploads.github.com/repos/$Repo/releases/$($rel.id)/assets?name=home-dumps.zip" `
            -Headers $headers -ContentType "application/zip" -InFile $ZipPath -TimeoutSec 3600
        if ($up.state -eq "uploaded" -and [int64]$up.size -eq $size) {
            Say "Пакет загружен в релиз: $ReleaseUrl" "Green"
            return $true
        }
        Say "Загрузка завершилась, но размер или состояние файла в релизе не совпали. Проверьте релиз вручную." "Red"
        return $false
    }
    catch {
        $msg = [string]$_.Exception.Message
        $msg = $msg.Replace($token, "***")
        Say "Ошибка загрузки в релиз: $msg" "Red"
        return $false
    }
}

function Show-ManualUploadHelp {
    Write-Host ""
    Say "Загрузите файл home-dumps.zip в релиз:" "Cyan"
    Write-Host "  1) в Firefox откройте: $ReleaseUrl"
    Write-Host "  2) нажмите значок карандаша (Edit) справа вверху;"
    Write-Host "  3) перетащите home-dumps.zip (окно проводника сейчас откроется) в область 'Attach binaries';"
    Write-Host "  4) дождитесь конца загрузки и нажмите 'Update release'."
    Write-Host "  Файлы prices.db.zip и prices-prev.db.zip не трогайте."
    Write-Host "  Дальше ничего делать не нужно: облако примет пакет при ближайшем запуске (21:30)"
    Write-Host "  и само удалит home-dumps.zip из релиза."
    Write-Host ""
    Start-Process explorer.exe -ArgumentList ("/select,`"" + $Zip + "`"")
}

# Основная работа. Возвращает код завершения (0 - успех).
function Invoke-HomeUpdate {
    param([string]$EffectiveMode)

    Set-Location $Backend

    # --- Предупреждение про время вечернего облачного запуска -----------------------
    $inCloudWindow = Test-CloudWindow
    if ($inCloudWindow) {
        Say "ВНИМАНИЕ: сейчас время вечернего облачного запуска (21:30). Пакет можно собрать, но загружать его в релиз лучше после 22:10." "Yellow"
    }

    # --- Шаг 1. Скачивание шести сетей ----------------------------------------------
    if (-not $PackOnly) {
        $lock = Join-Path $Backend "refresh.lock"
        if (Test-Path $lock) {
            Say "Найден файл refresh.lock (остался от оборванного запуска или идёт другой сбор):" "Red"
            Get-Content $lock | Out-Host
            Say "Если сейчас нигде не идёт сбор, удалите его командой:" "Yellow"
            Say "  Remove-Item $lock" "Yellow"
            Say "и запустите скрипт заново." "Yellow"
            return 1
        }
        Say "Шаг 1. Скачиваем шесть сетей (от 10 минут до часа и больше; окно не закрывайте)..."
        & (Join-Path $Backend "refresh_all.ps1") -Only $Chains | Out-Host
        Say "Скачивание завершено. Продолжаем." "Green"
    }
    else {
        Say "Шаг 1 пропущен (режим -PackOnly): упаковываем то, что уже лежит в dumps." "Yellow"
    }

    # --- Шаг 2. Отбор свежих файлов --------------------------------------------------
    Say "Шаг 2. Отбираем свежие файлы (не старше $MaxAgeDays дн.)..."
    New-Item -ItemType Directory -Force $Upload | Out-Null
    Remove-Item $Stage -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item $Zip -Force -ErrorAction SilentlyContinue

    foreach ($cloud in $Map.Keys) {
        $dst = Join-Path $Stage ("dumps\" + $cloud)
        New-Item -ItemType Directory -Force $dst | Out-Null
        foreach ($hf in $Map[$cloud]) {
            $src = Join-Path (Join-Path $Backend "dumps") $hf
            if (Test-Path $src) {
                robocopy $src $dst /S "/MAXAGE:$MaxAgeDays" /NFL /NDL /NJH /NJS /NP | Out-Null
                if ($LASTEXITCODE -ge 8) {
                    Say "Ошибка копирования из $src (код robocopy $LASTEXITCODE)." "Red"
                    return 1
                }
            }
        }
    }

    $report = foreach ($cloud in $Map.Keys) {
        $dir = Join-Path $Stage ("dumps\" + $cloud)
        $files = @(Get-ChildItem $dir -Recurse -File -ErrorAction SilentlyContinue)
        $sum = ($files | Measure-Object -Property Length -Sum).Sum
        if ($null -eq $sum) { $sum = 0 }
        [pscustomobject]@{
            "Папка"  = $cloud
            "Файлов" = $files.Count
            "МБ"     = [math]::Round($sum / 1MB, 1)
        }
    }
    ($report | Format-Table -AutoSize | Out-String -Width 200).TrimEnd() | Write-Host

    $total = ($report | Measure-Object -Property "Файлов" -Sum).Sum
    if (-not $total) {
        Say "Свежих файлов нет, пакет не создаём. Выполните шаг 1 (запустите скрипт без -PackOnly)." "Red"
        return 1
    }

    # --- Шаг 3. Упаковка -------------------------------------------------------------
    Say "Шаг 3. Упаковываем (несколько минут)..."
    Compress-Archive -Path (Join-Path $Stage "dumps") -DestinationPath $Zip -Force
    $zi = Get-Item $Zip
    $mb = [math]::Round($zi.Length / 1MB, 1)
    Say ("Готово: {0}  ({1} МБ)" -f $Zip, $mb) "Green"
    if ($zi.Length -gt 1.9GB) {
        Say "Файл больше 1,9 ГБ: GitHub не примет (лимит 2 ГБ). Запустите с ключами -PackOnly -MaxAgeDays 1." "Red"
        return 1
    }
    (Get-FileHash $Zip -Algorithm SHA256 | Format-List Hash | Out-String -Width 200).Trim() | Write-Host

    # --- Шаг 4. Доставка пакета ------------------------------------------------------
    if ($EffectiveMode -eq "upload") {
        if (Test-CloudWindow) {
            Say "Режим upload, но сейчас окно облачного запуска (21:00-22:10): в релиз не загружаем. Пакет лежит на диске, загрузите позже." "Yellow"
            return 0
        }
        Say "Шаг 4. Автоматическая загрузка в релиз..."
        $ok = Send-ToRelease -ZipPath $Zip
        if (-not $ok) {
            Say "Автозагрузка не удалась. Пакет готов на диске, загрузите его вручную:" "Yellow"
            if (-not $Auto) { Show-ManualUploadHelp }
            else { Write-Host "  Файл: $Zip ; релиз: $ReleaseUrl" }
            return 3
        }
        return 0
    }

    if ($Auto -and $EffectiveMode -eq "pack") {
        Say "Шаг 4. Пакет готов, загрузите его в релиз вручную." "Cyan"
        Show-ManualUploadHelp
        return 0
    }

    Say "Шаг 4. Загрузка в релиз вручную." "Cyan"
    Show-ManualUploadHelp
    return 0
}

# --- Определяем режим ---------------------------------------------------------------
$EffectiveMode = "manual"
if ($PSBoundParameters.ContainsKey("Mode")) {
    $EffectiveMode = $Mode
}
elseif ($Auto) {
    if (Test-Path $ModeFile) {
        $m = (Get-Content $ModeFile -Raw).Trim().ToLower()
        if ($m -in @("manual", "pack", "upload")) { $EffectiveMode = $m }
    }
}

$transcript = $false
if ($Auto) {
    New-Item -ItemType Directory -Force $LogDir | Out-Null
    Get-ChildItem $LogDir -Filter "home_update_*.log" -ErrorAction SilentlyContinue |
        Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-30) } |
        Remove-Item -Force -ErrorAction SilentlyContinue
    $logFile = Join-Path $LogDir ("home_update_{0}.log" -f (Get-Date -Format "yyyyMMdd_HHmmss"))
    try {
        Start-Transcript -Path $logFile | Out-Null
        $transcript = $true
    }
    catch { }
    Say ("Автозапуск {0}. Режим: {1}" -f (Get-Date -Format "dd.MM.yyyy HH:mm"), $EffectiveMode) "Cyan"
}

$exitCode = 0
try {
    if ($Auto -and $EffectiveMode -eq "manual") {
        Say "Режим manual: автоматически ничего не делаем (поменять режим: файл $ModeFile, слова manual / pack / upload)." "Yellow"
    }
    else {
        $result = @(Invoke-HomeUpdate -EffectiveMode $EffectiveMode)
        $exitCode = [int]$result[-1]
    }
}
catch {
    Say ("Непредвиденная ошибка: " + $_.Exception.Message) "Red"
    $exitCode = 1
}
finally {
    if ($transcript) {
        try { Stop-Transcript | Out-Null } catch { }
    }
}
exit $exitCode
