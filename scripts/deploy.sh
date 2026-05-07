#!/usr/bin/env bash
# =============================================================================
# 家藏书库 Home Library — 一键部署脚本
# 支持：Ubuntu / Debian / CentOS / macOS / 群晖 (SSH)
# 用法：bash deploy.sh [选项]
#   -p <端口>   HTTP 访问端口，默认 80
#   -s <密钥>   JWT 密钥（留空则自动生成）
#   -u <用户名> 管理员账号，默认 admin
#   -w <密码>   管理员初始密码，默认 Admin@123
#   -d          仅更新（跳过 Docker 安装检查）
# =============================================================================
set -euo pipefail

# ---------- 颜色输出 ----------
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
info()    { echo -e "${BLUE}[INFO]${NC}  $*"; }
success() { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

# ---------- 默认参数 ----------
HTTP_PORT=80
SECRET_KEY=""
ADMIN_USER="admin"
ADMIN_PASS="Admin@123"
UPDATE_ONLY=false
REPO_URL="https://github.com/lsgoodlionel/Home-Library.git"
INSTALL_DIR="$HOME/home-library"

# ---------- 解析参数 ----------
while getopts "p:s:u:w:d" opt; do
  case $opt in
    p) HTTP_PORT="$OPTARG" ;;
    s) SECRET_KEY="$OPTARG" ;;
    u) ADMIN_USER="$OPTARG" ;;
    w) ADMIN_PASS="$OPTARG" ;;
    d) UPDATE_ONLY=true ;;
    *) echo "用法: $0 [-p 端口] [-s 密钥] [-u 管理员] [-w 密码] [-d 仅更新]"; exit 1 ;;
  esac
done

echo ""
echo "=========================================================="
echo "   家藏书库 Home Library — 一键部署"
echo "=========================================================="
echo ""

# ---------- 检测操作系统 ----------
OS="unknown"
if [[ "$OSTYPE" == "darwin"* ]]; then
  OS="macos"
elif [[ -f /etc/debian_version ]]; then
  OS="debian"
elif [[ -f /etc/redhat-release ]] || [[ -f /etc/centos-release ]]; then
  OS="redhat"
elif [[ -f /etc/os-release ]] && grep -qi "synology" /etc/os-release 2>/dev/null; then
  OS="synology"
fi
info "检测到系统：$OS"

# ---------- 安装 Docker ----------
install_docker_debian() {
  info "安装 Docker（Debian/Ubuntu）..."
  sudo apt-get update -qq
  sudo apt-get install -y -qq ca-certificates curl gnupg lsb-release
  sudo install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/$(. /etc/os-release && echo "$ID")/gpg \
    | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  sudo chmod a+r /etc/apt/keyrings/docker.gpg
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
    https://download.docker.com/linux/$(. /etc/os-release && echo "$ID") \
    $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
  sudo apt-get update -qq
  sudo apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-compose-plugin
  sudo systemctl enable docker && sudo systemctl start docker
  # 将当前用户加入 docker 组（避免每次 sudo）
  sudo usermod -aG docker "$USER" 2>/dev/null || true
  success "Docker 安装完成"
}

install_docker_redhat() {
  info "安装 Docker（CentOS/RHEL）..."
  sudo yum install -y -q yum-utils
  sudo yum-config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo
  sudo yum install -y -q docker-ce docker-ce-cli containerd.io docker-compose-plugin
  sudo systemctl enable docker && sudo systemctl start docker
  sudo usermod -aG docker "$USER" 2>/dev/null || true
  success "Docker 安装完成"
}

if ! $UPDATE_ONLY; then
  if ! command -v docker &>/dev/null; then
    case $OS in
      debian)   install_docker_debian ;;
      redhat)   install_docker_redhat ;;
      macos)
        warn "macOS 请先安装 Docker Desktop：https://www.docker.com/products/docker-desktop/"
        warn "安装后重新运行本脚本（加 -d 跳过此检查）"
        open "https://www.docker.com/products/docker-desktop/" 2>/dev/null || true
        exit 1 ;;
      synology)
        warn "群晖请在 套件中心 安装 Container Manager，然后重新运行本脚本"
        exit 1 ;;
      *) error "无法自动安装 Docker，请手动安装后重试" ;;
    esac
  else
    success "Docker 已安装：$(docker --version | cut -d' ' -f3)"
  fi

  # 检查 docker compose（v2 插件）
  if ! docker compose version &>/dev/null; then
    error "未找到 docker compose（v2），请升级 Docker 到最新版本"
  fi
  success "Docker Compose 已就绪：$(docker compose version --short)"
fi

# ---------- 安装 Git ----------
if ! command -v git &>/dev/null; then
  case $OS in
    debian)  sudo apt-get install -y -qq git ;;
    redhat)  sudo yum install -y -q git ;;
    macos)   xcode-select --install 2>/dev/null || true ;;
    *) error "请先安装 git" ;;
  esac
fi

# ---------- 拉取 / 更新代码 ----------
if [[ -d "$INSTALL_DIR/.git" ]]; then
  info "更新代码..."
  cd "$INSTALL_DIR"
  git pull origin main
  success "代码已更新"
else
  info "克隆仓库到 $INSTALL_DIR ..."
  git clone "$REPO_URL" "$INSTALL_DIR"
  success "仓库克隆完成"
fi
cd "$INSTALL_DIR"

# ---------- 生成 .env ----------
if [[ -z "$SECRET_KEY" ]]; then
  SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))" 2>/dev/null \
    || openssl rand -hex 32 2>/dev/null \
    || cat /proc/sys/kernel/random/uuid 2>/dev/null | tr -d '-' \
    || date +%s | sha256sum | cut -c1-64)
fi

# 获取本机 IP（用于 CORS）
LOCAL_IP=$(hostname -I 2>/dev/null | awk '{print $1}' || ipconfig getifaddr en0 2>/dev/null || echo "localhost")

if [[ ! -f .env ]]; then
  info "生成 .env 配置文件..."
  cp .env.example .env
fi

# 写入关键配置（使用 sed 替换，保留注释结构）
sed_inplace() {
  if [[ "$OS" == "macos" ]]; then
    sed -i '' "$@"
  else
    sed -i "$@"
  fi
}

sed_inplace "s|^HTTP_PORT=.*|HTTP_PORT=${HTTP_PORT}|" .env
sed_inplace "s|^APP_SECRET_KEY=.*|APP_SECRET_KEY=${SECRET_KEY}|" .env
sed_inplace "s|^INITIAL_ADMIN_USERNAME=.*|INITIAL_ADMIN_USERNAME=${ADMIN_USER}|" .env
sed_inplace "s|^INITIAL_ADMIN_PASSWORD=.*|INITIAL_ADMIN_PASSWORD=${ADMIN_PASS}|" .env
sed_inplace "s|^CORS_ORIGINS=.*|CORS_ORIGINS=http://localhost,http://127.0.0.1,http://${LOCAL_IP}|" .env

success ".env 配置完成"

# ---------- 构建并启动 ----------
info "构建镜像并启动服务（首次约需 3-5 分钟）..."
docker compose pull --quiet 2>/dev/null || true
docker compose build --quiet
docker compose up -d --remove-orphans

# ---------- 等待健康检查 ----------
info "等待服务就绪..."
MAX_WAIT=120
ELAPSED=0
until docker compose ps backend | grep -q "healthy" || [[ $ELAPSED -ge $MAX_WAIT ]]; do
  sleep 3
  ELAPSED=$((ELAPSED + 3))
  printf "."
done
echo ""

if docker compose ps backend | grep -q "healthy"; then
  success "后端服务已就绪"
else
  warn "后端启动超时，查看日志：docker compose logs backend"
fi

# ---------- 部署完成 ----------
echo ""
echo "=========================================================="
echo -e "${GREEN}  部署成功！${NC}"
echo "=========================================================="
echo ""
echo "  访问地址："
echo -e "    本机：  ${BLUE}http://localhost:${HTTP_PORT}${NC}"
echo -e "    局域网：${BLUE}http://${LOCAL_IP}:${HTTP_PORT}${NC}"
echo ""
echo "  默认账号：${ADMIN_USER}"
echo "  默认密码：${ADMIN_PASS}  （首次登录后请立即修改）"
echo ""
echo "  常用命令："
echo "    查看日志：  docker compose -f $INSTALL_DIR/docker-compose.yml logs -f"
echo "    停止服务：  docker compose -f $INSTALL_DIR/docker-compose.yml down"
echo "    更新应用：  bash $INSTALL_DIR/scripts/deploy.sh -d"
echo ""
