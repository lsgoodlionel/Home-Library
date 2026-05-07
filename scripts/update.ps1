# =============================================================================
# 家藏书库 Home Library — Windows 智能更新脚本 (PowerShell)
# 用法：
#   .\update.ps1              # 有新版本才更新
#   .\update.ps1 -Force       # 强制重建
#   .\update.ps1 -Check       # 仅检查是否有新版本
#   .\update.ps1 -SetupAuto   # 配置 Windows 任务计划自动更新
#   .\update.ps1 -RemoveAuto  # 移除自动更新任务
# =============================================================================
param(
    [switch]$Force,
    [switch]$Check,
    [switch]$SetupAuto,
    [switch]$RemoveAuto,
    [string]$AutoTime = "03:00"   # 自动更新时间（24小时制）
)

$ErrorActionPreference = "Stop"
$InstallDir = "$env:USERPROFILE\home-library"
$LogDir     = "$InstallDir\logs"
$LogFile    = "$LogDir\update.log"
$TaskName   = "HomeLibraryAutoUpdate"

function Write-Log {
    param($Level, $Msg)
    $line = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') [$Level] $Msg"
    $line | Tee-Object -FilePath $LogFile -Append | Out-Host
}
function Write-Info    { Write-Log "INFO " $args[0] }
function Write-OK      { Write-Host "[OK]    $($args[0])" -ForegroundColor Green }
function Write-Warn    { Write-Log "WARN " $args[0] }
function Write-Err     { Write-Log "ERROR" $args[0]; exit 1 }

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

# ============================================================
# 移除自动更新任务
# ============================================================
if ($RemoveAuto) {
    try {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction Stop
        Write-OK "已移除自动更新任务：$TaskName"
    } catch {
        Write-Warn "任务不存在或移除失败：$_"
    }
    exit 0
}

# ============================================================
# 配置 Windows 任务计划（自动更新）
# ============================================================
if ($SetupAuto) {
    Write-Info "配置 Windows 任务计划，每天 $AutoTime 自动检查更新..."

    $ScriptPath = "$InstallDir\scripts\update.ps1"
    $Action  = New-ScheduledTaskAction `
        -Execute "powershell.exe" `
        -Argument "-ExecutionPolicy Bypass -NonInteractive -File `"$ScriptPath`"" `
        -WorkingDirectory $InstallDir

    # 每天指定时间运行
    $TimeParts = $AutoTime -split ":"
    $Trigger = New-ScheduledTaskTrigger -Daily -At "$($TimeParts[0]):$($TimeParts[1])"

    $Settings = New-ScheduledTaskSettingsSet `
        -ExecutionTimeLimit (New-TimeSpan -Minutes 30) `
        -StartWhenAvailable `
        -RunOnlyIfNetworkAvailable

    # 以当前用户身份运行（无需管理员）
    $Principal = New-ScheduledTaskPrincipal `
        -UserId "$env:USERDOMAIN\$env:USERNAME" `
        -LogonType S4U `
        -RunLevel Limited

    try {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    } catch {}

    Register-ScheduledTask `
        -TaskName  $TaskName `
        -Action    $Action `
        -Trigger   $Trigger `
        -Settings  $Settings `
        -Principal $Principal `
        -Description "家藏书库 Home Library 自动更新" | Out-Null

    Write-OK "任务计划已创建：$TaskName（每天 $AutoTime 检查更新）"
    Write-Host ""
    Write-Host "  管理命令：" -ForegroundColor Cyan
    Write-Host "    立即运行：Start-ScheduledTask -TaskName '$TaskName'"
    Write-Host "    查看状态：Get-ScheduledTask -TaskName '$TaskName' | Get-ScheduledTaskInfo"
    Write-Host "    停止自动：.\update.ps1 -RemoveAuto"
    exit 0
}

# ============================================================
# 检查依赖
# ============================================================
try { docker --version | Out-Null } catch { Write-Err "未找到 docker，请先完成部署" }
try { git --version | Out-Null }    catch { Write-Err "未找到 git" }

if (-not (Test-Path "$InstallDir\.git")) {
    Write-Err "未找到项目目录 $InstallDir，请先运行 deploy.ps1"
}
Set-Location $InstallDir

# ============================================================
# 1. 检查是否有新版本
# ============================================================
Write-Info "检查远端更新..."
git fetch origin main --quiet 2>&1 | Out-Null

$LocalSHA  = git rev-parse HEAD
$RemoteSHA = git rev-parse origin/main
$CurrentVer = (git describe --tags --always 2>$null) ?? $LocalSHA.Substring(0,7)
$LatestVer  = (git describe --tags --always origin/main 2>$null) ?? $RemoteSHA.Substring(0,7)

if ($LocalSHA -eq $RemoteSHA -and -not $Force) {
    Write-OK "已是最新版本（$CurrentVer），无需更新"
    exit 0
}

$Changelog = git log --oneline "origin/main" "^$LocalSHA" 2>$null | Select-Object -First 10

if ($Check) {
    if ($LocalSHA -ne $RemoteSHA) {
        Write-Host "发现新版本：$CurrentVer → $LatestVer"
        Write-Host "`n更新内容："
        $Changelog | ForEach-Object { Write-Host "  • $_" }
    } else {
        Write-Host "已是最新版本（$CurrentVer）"
    }
    exit 0
}

Write-Info "发现新版本：$CurrentVer → $LatestVer"
if ($Changelog) {
    Write-Host "更新内容："; $Changelog | ForEach-Object { Write-Host "  • $_" }
}

# ============================================================
# 2. 备份数据库
# ============================================================
Write-Info "备份数据库..."
$Timestamp  = Get-Date -Format "yyyyMMdd_HHmmss"
$BackupDir  = "$InstallDir\backups"
New-Item -ItemType Directory -Force -Path $BackupDir | Out-Null

$running = docker compose ps backend 2>&1 | Select-String "Up|running"
if ($running) {
    docker compose exec -T backend sh -c "sqlite3 /data/home_library.sqlite3 `".backup /backups/pre_update_${Timestamp}.sqlite3`"" 2>&1 | Out-Null
    Write-OK "数据库已备份"
}

# 清理 7 天前的备份
Get-ChildItem "$BackupDir\pre_update_*.sqlite3" -ErrorAction SilentlyContinue |
    Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-7) } |
    Remove-Item -Force

# ============================================================
# 3. 拉取最新代码
# ============================================================
Write-Info "拉取最新代码..."
git pull origin main --ff-only 2>&1
Write-OK "代码已更新至 $LatestVer"

# ============================================================
# 4. 重建并重启
# ============================================================
Write-Info "重建镜像..."
docker compose build --quiet

Write-Info "重启服务..."
docker compose up -d --remove-orphans

# 等待健康检查
Write-Info "等待服务就绪..."
$maxWait = 120; $elapsed = 0
do {
    Start-Sleep 3; $elapsed += 3
    $status = docker compose ps backend 2>&1
    if ($status -match "healthy") { break }
    Write-Host "." -NoNewline
} while ($elapsed -lt $maxWait)
Write-Host ""

if (docker compose ps backend 2>&1 | Select-String "healthy") {
    Write-OK "服务已就绪"
} else {
    Write-Warn "服务启动超时，请检查：docker compose logs backend"
}

# ============================================================
# 清理旧镜像
# ============================================================
docker image prune -f 2>&1 | Out-Null

# ============================================================
# 完成
# ============================================================
Write-OK "✅ 更新完成：$CurrentVer → $LatestVer"
