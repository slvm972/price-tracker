<#
.SYNOPSIS
  Обновление «капризных» сетей с домашнего ПК и подготовка пакета для облака.

.DESCRIPTION
  1) запускает refresh_all.ps1 только для шести сетей, которые облако собрать не может;
  2) отбирает свежие файлы этих сетей (по умолчанию не старше 3 дней),
     переименовывает папки под облачные названия и упаковывает всё в D:\1\upload\home-dumps.zip;
  3) подсказывает, как загрузить файл в релиз db-latest.
  Облако само примет пакет при ближайшем запуске и удалит его из релиза.

.EXAMPLE
  pwsh -NoProfile -ExecutionPolicy Bypass -File D:\1\price-tracker\home_update.ps1

.EXAMPLE
  # только упаковать то, что уже скачано (без нового скачивания)
  pwsh -NoProfile -ExecutionPolicy Bypass -File D:\1\price-tracker\home_update.ps1 -PackOnly

.EXAMPLE
  # если файл получился больше 1,9 ГБ — взять только файлы за последний день
  pwsh -NoProfile -ExecutionPolicy Bypass -File D:\1\price-tracker\home_update.ps1 -PackOnly -MaxAgeDays 1
#>

param(
    [switch]$PackOnly,
    [int]$MaxAgeDays = 3
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"

$Backend    = "D:\1\price-tracker"
$Upload     = "D:\1\upload"
$Stage      = Join-Path $Upload "home-dumps-stage"
$Zip        = Join-Path $Upload "home-dumps.zip"
$ReleaseUrl = "https://github.com/slvm972/price-tracker/releases/tag/db-latest"

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

Set-Location $Backend

# --- Предупреждение про время вечернего облачного запуска -----------------------
$now = Get-Date
$inCloudWindow = (($now.Hour -eq 21 -and $now.Minute -ge 10) -or ($now.Hour -eq 22 -and $now.Minute -le 5))
if ($inCloudWindow) {
    Say "ВНИМАНИЕ: сейчас время вечернего облачного запуска (21:30). Пакет можно собрать, но загружать его в релиз лучше после 22:05." "Yellow"
}

# --- Шаг 1. Скачивание шести сетей ------------------------------------------------
if (-not $PackOnly) {
    $lock = Join-Path $Backend "refresh.lock"
    if (Test-Path $lock) {
        Say "Найден файл refresh.lock (остался от оборванного запуска):" "Red"
        Get-Content $lock
        Say "Если сейчас нигде не идёт сбор, удалите его командой:" "Yellow"
        Say "  Remove-Item $lock" "Yellow"
        Say "и запустите скрипт заново." "Yellow"
        exit 1
    }
    Say "Шаг 1. Скачиваем шесть сетей (от 10 минут до часа и больше; окно не закрывайте)..."
    & (Join-Path $Backend "refresh_all.ps1") -Only $Chains
    Say "Скачивание завершено. Продолжаем." "Green"
}
else {
    Say "Шаг 1 пропущен (режим -PackOnly): упаковываем то, что уже лежит в dumps." "Yellow"
}

# --- Шаг 2. Отбор свежих файлов ----------------------------------------------------
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
                exit 1
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
$report | Format-Table -AutoSize

$total = ($report | Measure-Object -Property "Файлов" -Sum).Sum
if (-not $total) {
    Say "Свежих файлов нет, пакет не создаём. Выполните шаг 1 (запустите скрипт без -PackOnly)." "Red"
    exit 1
}

# --- Шаг 3. Упаковка ---------------------------------------------------------------
Say "Шаг 3. Упаковываем (несколько минут)..."
Compress-Archive -Path (Join-Path $Stage "dumps") -DestinationPath $Zip -Force
$zi = Get-Item $Zip
$mb = [math]::Round($zi.Length / 1MB, 1)
Say ("Готово: {0}  ({1} МБ)" -f $Zip, $mb) "Green"
if ($zi.Length -gt 1.9GB) {
    Say "Файл больше 1,9 ГБ: GitHub не примет (лимит 2 ГБ). Запустите с ключами -PackOnly -MaxAgeDays 1." "Red"
    exit 1
}
Get-FileHash $Zip -Algorithm SHA256 | Format-List Hash

# --- Шаг 4. Что делать дальше ------------------------------------------------------
Write-Host ""
Say "Шаг 4. Загрузите файл home-dumps.zip в релиз:" "Cyan"
Write-Host "  1) в Firefox откройте: $ReleaseUrl"
Write-Host "  2) нажмите значок карандаша (Edit) справа вверху;"
Write-Host "  3) перетащите home-dumps.zip (окно проводника сейчас откроется) в область 'Attach binaries';"
Write-Host "  4) дождитесь конца загрузки и нажмите 'Update release'."
Write-Host "  Файлы prices.db.zip и prices-prev.db.zip не трогайте."
Write-Host "  Дальше ничего делать не нужно: облако примет пакет при ближайшем запуске (21:30)"
Write-Host "  и само удалит home-dumps.zip из релиза."
Write-Host ""
Start-Process explorer.exe -ArgumentList ("/select,`"" + $Zip + "`"")
