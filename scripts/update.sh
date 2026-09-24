#!/usr/bin/env bash
# =============================================================================
# 家藏书库 Home Library — 升级脚本
#
# 默认使用预构建镜像（推荐，速度快）：
#   bash update.sh              # 拉取最新镜像并重启
#   bash update.sh --version 0.1.50   # 升级到指定版本
#   bash update.sh --check      # 仅检查当前运行版本
#   bash update.sh --source     # 从源码构建（传统方式，速度慢）
#
# 环境变量（可在 .env 中设置）：
#   UPDATE_NOTIFY_URL   Webhook 通知地址（企业微信 / 钉钉 / Slack）
#   UPDATE_BACKUP_KEEP  备份保留天数，默认 7
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="$(dirname "$SCRIPT_DIR")"
PROD_COMPOSE="$INSTALL_DIR/docker-compose.prod.yml"
SRC_COMPOSE="$INSTALL_DIR/docker-compose.yml"
LOG_DIR="$INSTALL_DIR/logs"
LOG_FILE="$LOG_DIR/update.log"
LOCK_FILE="/tmp/home-library-update.lock"

# ---------- 参数 ----------
TARGET_VERSION="latest"
CHECK_ONLY=false
SOURCE_BUILD=false

for arg in "$@"; do
  case $arg in
    --check)   CHECK_ONLY=true ;;
    --source)  SOURCE_BUILD=true ;;
    --version) shift; TARGET_VERSION="$1" ;;
    --version=*) TARGET_VERSION="${arg#--version=}" ;;
  esac
done

# ---------- 颜色 ----------
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'

mkdir -p "$LOG_DIR"
_log() { local level="$1"; shift; echo -e "$(date '+%Y-%m-%d %H:%M:%S') [$level] $*" | tee -a "$LOG_FILE"; }
info()    { _log "INFO " "${BLUE}$*${NC}"; }
success() { _log "OK   " "${GREEN}$*${NC}"; }
warn()    { _log "WARN " "${YELLOW}$*${NC}"; }
error()   { _log "ERROR" "${RED}$*${NC}"; exit 1; }

# ---------- 防并发 ----------
if [[ -f "$LOCK_FILE" ]]; then
  pid=$(cat "$LOCK_FILE")
  if kill -0 "$pid" 2>/dev/null; then
    warn "另一个更新进程正在运行（PID $pid），跳过本次"
    exit 0
  fi
fi
echo $$ > "$LOCK_FILE"
trap 'rm -f "$LOCK_FILE"' EXIT

command -v docker >/dev/null || error "未找到 docker"
docker compose version >/dev/null 2>&1 || error "未找到 docker compose (v2)"

# ==========================================================================
# 检查当前版本
# ==========================================================================
CURRENT_VERSION="unknown"
if docker compose -f "$PROD_COMPOSE" ps backend 2>/dev/null | grep -qiE "running|up"; then
  CURRENT_VERSION=$(docker compose -f "$PROD_COMPOSE" exec -T backend \
    sh -c 'python -c "from app.core.config import get_settings; print(get_settings().app_version)"' \
    2>/dev/null | tr -d '\r' || echo "unknown")
elif docker compose ps backend 2>/dev/null | grep -qiE "running|up"; then
  CURRENT_VERSION=$(docker compose exec -T backend \
    sh -c 'python -c "from app.core.config import get_settings; print(get_settings().app_version)"' \
    2>/dev/null | tr -d '\r' || echo "unknown")
fi

if $CHECK_ONLY; then
  echo "当前运行版本：$CURRENT_VERSION"
  exit 0
fi

# ==========================================================================
# 备份数据库
# ==========================================================================
BACKUP_KEEP="${UPDATE_BACKUP_KEEP:-7}"
BACKUP_DIR="$INSTALL_DIR/backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
mkdir -p "$BACKUP_DIR"

_do_backup() {
  local compose_file="$1"
  if docker compose -f "$compose_file" ps backend 2>/dev/null | grep -qiE "running|up"; then
    docker compose -f "$compose_file" exec -T backend sh -c \
      "sqlite3 /data/home_library.sqlite3 \".backup /backups/pre_update_${TIMESTAMP}.sqlite3\"" \
      2>/dev/null || true
    local f="$BACKUP_DIR/pre_update_${TIMESTAMP}.sqlite3"
    [[ -f "$f" ]] && gzip -f "$f" && success "数据库已备份：${f}.gz"
  fi
  find "$BACKUP_DIR" -name "pre_update_*.gz" -mtime "+$BACKUP_KEEP" -delete 2>/dev/null || true
}

# ==========================================================================
# 预构建镜像升级（默认）
# ==========================================================================
if ! $SOURCE_BUILD; then
  if [[ ! -f "$PROD_COMPOSE" ]]; then
    error "未找到 $PROD_COMPOSE，请先拉取最新代码：git pull origin main"
  fi

  info "升级模式：预构建镜像（ghcr.io），目标版本：${TARGET_VERSION}"
  info "备份数据库..."
  _do_backup "$PROD_COMPOSE"

  info "拉取镜像..."
  VERSION="$TARGET_VERSION" docker compose -f "$PROD_COMPOSE" pull

  info "重启服务..."
  VERSION="$TARGET_VERSION" docker compose -f "$PROD_COMPOSE" up -d --remove-orphans

  info "等待服务就绪..."
  MAX_WAIT=120; ELAPSED=0
  until VERSION="$TARGET_VERSION" docker compose -f "$PROD_COMPOSE" ps backend \
      2>/dev/null | grep -qiE "healthy"; do
    [[ $ELAPSED -ge $MAX_WAIT ]] && break
    sleep 3; ELAPSED=$((ELAPSED + 3)); printf "."
  done
  echo ""

  docker image prune -f 2>/dev/null || true

  NEW_VERSION=$(VERSION="$TARGET_VERSION" docker compose -f "$PROD_COMPOSE" exec -T backend \
    sh -c 'python -c "from app.core.config import get_settings; print(get_settings().app_version)"' \
    2>/dev/null | tr -d '\r' || echo "$TARGET_VERSION")

  success "✅ 升级完成：$CURRENT_VERSION → $NEW_VERSION"

# ==========================================================================
# 从源码构建升级（--source 模式）
# ==========================================================================
else
  command -v git >/dev/null || error "未找到 git（source 模式需要 git）"
  info "升级模式：从源码构建"
  cd "$INSTALL_DIR"

  info "检查远端更新..."
  git fetch origin main --quiet
  LOCAL_SHA=$(git rev-parse HEAD)
  REMOTE_SHA=$(git rev-parse origin/main)

  if [[ "$LOCAL_SHA" == "$REMOTE_SHA" ]]; then
    success "已是最新版本（$CURRENT_VERSION），无需更新"
    exit 0
  fi

  info "备份数据库..."
  _do_backup "$SRC_COMPOSE"

  info "拉取最新代码..."
  git pull origin main --ff-only || git pull origin main --rebase

  info "重建镜像并重启..."
  docker compose -f "$SRC_COMPOSE" build --quiet
  docker compose -f "$SRC_COMPOSE" up -d --remove-orphans

  info "等待服务就绪..."
  MAX_WAIT=120; ELAPSED=0
  until docker compose ps backend 2>/dev/null | grep -qiE "healthy"; do
    [[ $ELAPSED -ge $MAX_WAIT ]] && break
    sleep 3; ELAPSED=$((ELAPSED + 3)); printf "."
  done
  echo ""

  docker image prune -f 2>/dev/null || true
  success "✅ 升级完成：$CURRENT_VERSION → $(git describe --tags --always 2>/dev/null || git rev-parse --short HEAD)"
fi

# ==========================================================================
# 可选通知
# ==========================================================================
NOTIFY_URL="${UPDATE_NOTIFY_URL:-}"
if [[ -n "$NOTIFY_URL" ]]; then
  curl -s -X POST "$NOTIFY_URL" \
    -H "Content-Type: application/json" \
    -d "{\"event\":\"update\",\"from\":\"${CURRENT_VERSION}\",\"to\":\"${TARGET_VERSION}\",\"time\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"}" \
    >/dev/null 2>&1 || true
  info "已发送更新通知"
fi
