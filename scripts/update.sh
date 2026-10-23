#!/usr/bin/env bash
# =============================================================================
# 家藏书库 Home Library — 升级脚本
#
# 默认使用预构建镜像（推荐，速度快）：
#   bash update.sh              # 拉取最新镜像并重启
#   bash update.sh --version 0.1.50   # 升级到指定版本
#   bash update.sh --check      # 仅检查当前运行版本
#   bash update.sh --source     # 从源码构建（传统方式，速度慢）
#   bash update.sh --install-dir /opt/home-library
#
# 环境变量（可在 .env 中设置）：
#   UPDATE_NOTIFY_URL   Webhook 通知地址（企业微信 / 钉钉 / Slack）
#   UPDATE_BACKUP_KEEP  备份保留天数，默认 7
# =============================================================================
set -euo pipefail

LOCK_FILE="/tmp/home-library-update.lock"

# ---------- 参数 ----------
TARGET_VERSION="latest"
CHECK_ONLY=false
SOURCE_BUILD=false
SCRIPT_SOURCE="${BASH_SOURCE[0]}"

case "$SCRIPT_SOURCE" in
  /dev/fd/*|/proc/*/fd/*)
    DEFAULT_INSTALL_DIR="$HOME/home-library"
    ;;
  *)
    SCRIPT_DIR="$(cd "$(dirname "$SCRIPT_SOURCE")" && pwd)"
    DEFAULT_INSTALL_DIR="$(dirname "$SCRIPT_DIR")"
    ;;
esac

INSTALL_DIR="$DEFAULT_INSTALL_DIR"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --check)
      CHECK_ONLY=true
      shift
      ;;
    --source)
      SOURCE_BUILD=true
      shift
      ;;
    --auto)
      shift
      ;;
    --version)
      [[ $# -ge 2 ]] || { echo "错误：--version 缺少版本号" >&2; exit 2; }
      TARGET_VERSION="$2"
      shift 2
      ;;
    --version=*)
      TARGET_VERSION="${1#--version=}"
      [[ -n "$TARGET_VERSION" ]] || { echo "错误：--version 缺少版本号" >&2; exit 2; }
      shift
      ;;
    --install-dir)
      [[ $# -ge 2 ]] || { echo "错误：--install-dir 缺少路径" >&2; exit 2; }
      INSTALL_DIR="$2"
      shift 2
      ;;
    --install-dir=*)
      INSTALL_DIR="${1#--install-dir=}"
      [[ -n "$INSTALL_DIR" ]] || { echo "错误：--install-dir 缺少路径" >&2; exit 2; }
      shift
      ;;
    -h|--help)
      echo "用法：bash update.sh [--check] [--source] [--version VERSION] [--install-dir PATH]"
      exit 0
      ;;
    *)
      echo "错误：未知参数 $1" >&2
      exit 2
      ;;
  esac
done

PROD_COMPOSE="$INSTALL_DIR/docker-compose.prod.yml"
SRC_COMPOSE="$INSTALL_DIR/docker-compose.yml"
LOG_DIR="$INSTALL_DIR/logs"
LOG_FILE="$LOG_DIR/update.log"

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
[[ "$BACKUP_KEEP" =~ ^[0-9]+$ ]] \
  || error "UPDATE_BACKUP_KEEP 必须是非负整数"
BACKUP_DIR="$INSTALL_DIR/backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
mkdir -p "$BACKUP_DIR"

_do_backup() {
  local compose_file="$1"
  if docker compose -f "$compose_file" ps backend 2>/dev/null | grep -qiE "running|up"; then
    local backup_path="/backups/pre_update_${TIMESTAMP}.sqlite3"
    if ! docker compose -f "$compose_file" exec -T backend sh -c \
      "sqlite3 /data/home_library.sqlite3 \".backup ${backup_path}\" && test -s ${backup_path}"; then
      error "数据库备份失败，已停止更新；请检查数据库和 backups 数据卷"
    fi
    success "数据库已备份并验证：Docker backups 数据卷 ${backup_path}"
    docker compose -f "$compose_file" exec -T backend sh -c \
      "find /backups -name 'pre_update_*.sqlite3' -mtime +${BACKUP_KEEP} -delete" \
      >/dev/null 2>&1 || warn "旧备份清理失败，本次已验证备份仍保留"
  else
    error "后端容器未运行，无法验证数据库备份，已停止更新"
  fi
}

_sync_main_checkout() {
  if [[ ! -d "$INSTALL_DIR/.git" ]]; then
    warn "安装目录不是 Git 仓库，跳过部署文件同步"
    return
  fi

  command -v git >/dev/null || error "安装目录是 Git 仓库，但未找到 git"

  local tracked_changes
  tracked_changes=$(git -C "$INSTALL_DIR" status --porcelain --untracked-files=no)
  if [[ -n "$tracked_changes" ]]; then
    error "检测到未提交的部署文件修改，已停止更新以避免覆盖；请先提交或备份这些修改"
  fi

  info "同步 GitHub main 部署文件..."
  git -C "$INSTALL_DIR" fetch origin main --no-tags --prune --quiet

  local current_sha target_sha current_short backup_branch
  current_sha=$(git -C "$INSTALL_DIR" rev-parse HEAD)
  target_sha=$(git -C "$INSTALL_DIR" rev-parse 'origin/main^{commit}')
  if [[ "$current_sha" == "$target_sha" ]]; then
    success "部署文件已与 GitHub main 同步"
    return
  fi

  if ! git -C "$INSTALL_DIR" merge-base --is-ancestor "$current_sha" "$target_sha"; then
    current_short=$(git -C "$INSTALL_DIR" rev-parse --short "$current_sha")
    backup_branch="backup/home-library-update/${TIMESTAMP}-${current_short}"
    if git -C "$INSTALL_DIR" show-ref --verify --quiet "refs/heads/$backup_branch"; then
      backup_branch="${backup_branch}-$$"
    fi
    git -C "$INSTALL_DIR" branch "$backup_branch" "$current_sha"
    warn "检测到 GitHub main 历史回退或分叉，原提交已保存在本地分支 $backup_branch"
  fi

  git -C "$INSTALL_DIR" reset --hard "$target_sha" >/dev/null
  success "部署文件已同步到 $(git -C "$INSTALL_DIR" rev-parse --short HEAD)"
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

  _sync_main_checkout

  if [[ ! -f "$PROD_COMPOSE" ]]; then
    error "同步后未找到 $PROD_COMPOSE"
  fi

  info "拉取镜像..."
  VERSION="$TARGET_VERSION" docker compose -f "$PROD_COMPOSE" pull

  info "重启服务..."
  VERSION="$TARGET_VERSION" docker compose -f "$PROD_COMPOSE" up -d --remove-orphans

  info "等待服务就绪..."
  MAX_WAIT="${UPDATE_MAX_WAIT:-120}"
  [[ "$MAX_WAIT" =~ ^[0-9]+$ ]] || error "UPDATE_MAX_WAIT 必须是非负整数秒"
  ELAPSED=0
  until VERSION="$TARGET_VERSION" docker compose -f "$PROD_COMPOSE" ps backend \
      2>/dev/null | grep -qiE "healthy"; do
    [[ $ELAPSED -ge $MAX_WAIT ]] && break
    sleep 3; ELAPSED=$((ELAPSED + 3)); printf "."
  done
  echo ""

  if ! VERSION="$TARGET_VERSION" docker compose -f "$PROD_COMPOSE" ps backend \
      2>/dev/null | grep -qiE "healthy"; then
    error "更新后端在 ${MAX_WAIT} 秒内未恢复健康；数据库备份保留在 Docker backups 数据卷，请检查容器日志后人工恢复"
  fi

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
  [[ -d "$INSTALL_DIR/.git" ]] \
    || error "source 模式要求安装目录是 Git 仓库，不能在未同步源码的目录中构建"
  info "升级模式：从源码构建"
  cd "$INSTALL_DIR"

  info "备份数据库..."
  _do_backup "$SRC_COMPOSE"

  _sync_main_checkout

  info "重建镜像并重启..."
  docker compose -f "$SRC_COMPOSE" build --quiet
  docker compose -f "$SRC_COMPOSE" up -d --remove-orphans

  info "等待服务就绪..."
  MAX_WAIT="${UPDATE_MAX_WAIT:-120}"
  [[ "$MAX_WAIT" =~ ^[0-9]+$ ]] || error "UPDATE_MAX_WAIT 必须是非负整数秒"
  ELAPSED=0
  until docker compose ps backend 2>/dev/null | grep -qiE "healthy"; do
    [[ $ELAPSED -ge $MAX_WAIT ]] && break
    sleep 3; ELAPSED=$((ELAPSED + 3)); printf "."
  done
  echo ""

  if ! docker compose ps backend 2>/dev/null | grep -qiE "healthy"; then
    error "源码更新后端在 ${MAX_WAIT} 秒内未恢复健康；数据库备份已保留，请检查容器日志后人工恢复"
  fi

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
