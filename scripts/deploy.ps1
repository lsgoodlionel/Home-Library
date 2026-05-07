# =============================================================================
# 家藏书库 Home Library — Windows 一键部署脚本 (PowerShell)
# 支持：Windows 10/11（需已安装 Docker Desktop）
# 用法：右键 → 以管理员身份运行 PowerShell，执行：
#   .\deploy.ps1
# 或带参数：
#   .\deploy.ps1 -Port 8080 -AdminUser admin -AdminPass MyPass123
# =============================================================================
param(
    [int]$Port       = 80,
    [string]$Secret  = "",
    [string]$AdminUser = "admin",
    [string]$AdminPass = "Admin@123",
    [switch]$UpdateOnly
)

$ErrorActionPreference = "Stop"

# ---------- 颜色输出 ----------
function Write-Info   { param($msg) Write-Host "[INFO]  $msg" -ForegroundColor Cyan }
function Write-OK     { param($msg) Write-Host "[OK]    $msg" -ForegroundColor Green }
function Write-Warn   { param($msg) Write-Host "[WARN]  $msg" -ForegroundColor Yellow }
function Write-Err    { param($msg) Write-Host "[ERROR] $msg" -ForegroundColor Red; exit 1 }

$REPO_URL   = "https://github.com/lsgoodlionel/Home-Library.git"
$InstallDir = "$env:USERPROFILE\home-library"

Write-Host ""
Write-Host "==========================================================" -ForegroundColor Blue
Write-Host "   家藏书库 Home Library — Windows 一键部署" -ForegroundColor Blue
Write-Host "==========================================================" -ForegroundColor Blue
Write-Host ""

# ---------- 检查 Docker Desktop ----------
if (-not $UpdateOnly) {
    try {
        $dockerVer = docker --version 2>&1
        Write-OK "Docker 已安装：$dockerVer"
    } catch {
        Write-Warn "未检测到 Docker Desktop，正在打开下载页面..."
        Start-Process "https://www.docker.com/products/docker-desktop/"
        Write-Err "请安装 Docker Desktop 后重新运行本脚本`n下载地址：https://www.docker.com/products/docker-desktop/"
    }

    try {
        docker compose version | Out-Null
        Write-OK "Docker Compose 已就绪"
    } catch {
        Write-Err "未找到 docker compose（v2），请升级 Docker Desktop 到最新版本"
    }
}

# ---------- 检查 Git ----------
try {
    git --version | Out-Null
} catch {
    Write-Warn "未检测到 Git，正在打开下载页面..."
    Start-Process "https://git-scm.com/download/win"
    Write-Err "请安装 Git 后重新运行本脚本`n下载地址：https://git-scm.com/download/win"
}

# ---------- 拉取 / 更新代码 ----------
if (Test-Path "$InstallDir\.git") {
    Write-Info "更新代码..."
    Set-Location $InstallDir
    git pull origin main
    Write-OK "代码已更新"
} else {
    Write-Info "克隆仓库到 $InstallDir ..."
    git clone $REPO_URL $InstallDir
    Write-OK "仓库克隆完成"
}
Set-Location $InstallDir

# ---------- 生成 .env ----------
if (-not $Secret) {
    # PowerShell 生成随机密钥
    $bytes = New-Object byte[] 32
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    $Secret = -join ($bytes | ForEach-Object { $_.ToString("x2") })
}

# 获取本机 IP
$LocalIP = (Get-NetIPAddress -AddressFamily IPv4 -InterfaceAlias "Ethernet*","Wi-Fi*" `
    -ErrorAction SilentlyContinue | Where-Object { $_.IPAddress -notlike "169.*" } `
    | Select-Object -First 1).IPAddress
if (-not $LocalIP) { $LocalIP = "localhost" }

if (-not (Test-Path ".env")) {
    Write-Info "生成 .env 配置文件..."
    Copy-Item ".env.example" ".env"
}

# 替换关键配置
$env_content = Get-Content ".env" -Raw
$env_content = $env_content -replace "(?m)^HTTP_PORT=.*",               "HTTP_PORT=$Port"
$env_content = $env_content -replace "(?m)^APP_SECRET_KEY=.*",          "APP_SECRET_KEY=$Secret"
$env_content = $env_content -replace "(?m)^INITIAL_ADMIN_USERNAME=.*",  "INITIAL_ADMIN_USERNAME=$AdminUser"
$env_content = $env_content -replace "(?m)^INITIAL_ADMIN_PASSWORD=.*",  "INITIAL_ADMIN_PASSWORD=$AdminPass"
$env_content = $env_content -replace "(?m)^CORS_ORIGINS=.*",            "CORS_ORIGINS=http://localhost,http://127.0.0.1,http://$LocalIP"
$env_content | Set-Content ".env" -NoNewline
Write-OK ".env 配置完成"

# ---------- 构建并启动 ----------
Write-Info "构建镜像并启动服务（首次约需 3-5 分钟）..."
docker compose build --quiet
docker compose up -d --remove-orphans

# ---------- 等待健康检查 ----------
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
    Write-OK "后端服务已就绪"
} else {
    Write-Warn "后端启动超时，查看日志：docker compose logs backend"
}

# ---------- 部署完成 ----------
Write-Host ""
Write-Host "==========================================================" -ForegroundColor Green
Write-Host "  部署成功！" -ForegroundColor Green
Write-Host "==========================================================" -ForegroundColor Green
Write-Host ""
Write-Host "  访问地址："
Write-Host "    本机：   http://localhost:$Port" -ForegroundColor Cyan
Write-Host "    局域网： http://${LocalIP}:$Port" -ForegroundColor Cyan
Write-Host ""
Write-Host "  默认账号：$AdminUser"
Write-Host "  默认密码：$AdminPass  （首次登录后请立即修改）"
Write-Host ""
Write-Host "  常用命令："
Write-Host "    查看日志：  docker compose -f $InstallDir\docker-compose.yml logs -f"
Write-Host "    停止服务：  docker compose -f $InstallDir\docker-compose.yml down"
Write-Host "    更新应用：  .\deploy.ps1 -UpdateOnly"
Write-Host ""

# 自动打开浏览器
Start-Process "http://localhost:$Port"
