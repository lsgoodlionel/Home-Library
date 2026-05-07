#!/usr/bin/env bash
# =============================================================================
# 家藏书库 Home Library — 智能更新脚本
# 支持：Ubuntu / Debian / CentOS / macOS / 群晖
#
# 用法：
#   bash update.sh              # 有新版本才更新
#   bash update.sh --force      # 强制重建（即使无新版本）
#   bash update.sh --check      # 仅检查是否有新版本，不执行更新
#   bash update.sh --auto       # 自动模式（供 cron/systemd 调用，成功后发通知）
#
# 环境变量（可在 .env 中设置）：
#   UPDATE_NOTIFY_URL   Webhook 地址（支持企业微信/钉钉/Slack/自定义）
#   UPDATE_BACKUP_KEEP  保留备份天数，默认 7
#   UPDATE_LOG          日志文件路径，默认 ~/home-library/logs/update.log
# =============================================================================
set -euo pipefail

# ---------- 路径配置 ----------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="$(dirname "$SCRIPT_DIR")"
LOG_DIR="$INSTALL_DIR/logs"
LOG_FILE="${UPDATE_LOG:-$LOG_DIR/update.log}"
LOCK_FILE="/tmp/home-library-update.lock"

# ---------- 参数解析 ----------
FORCE=false
CHECK_ONLY=false
AUTO_MODE=false

for arg in "$@"; do
  case $arg in
    --force)  FORCE=true ;;
    --check)  CHECK_ONLY=true ;;
    --auto)   AUTO_MODE=true ;;
  esac
done

# ---------- 颜色（非 auto 模式才彩色） ----------
if $AUTO_MODE; then
  RED=''; GREEN=''; YELLOW=''; BLUE=''; NC=''
else
  RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
fi

# ---------- 日志函数（同时写文件） ----------
mkdir -p "$LOG_DIR"
_log() { local level="$1"; shift; echo -e "$(date '+%Y-%m-%d %H:%M:%S') [$level] $*" | tee -a "$LOG_FILE"; }
info()    { _log "INFO " "${BLUE}$*${NC}"; }
success() { _log "OK   " "${GREEN}$*${NC}"; }
warn()    { _log "WARN " "${YELLOW}$*${NC}"; }
error()   { _log "ERROR" "${RED}$*${NC}"; exit 1; }

# ---------- 防并发锁 ----------
if [[ -f "$LOCK_FILE" ]]; then
  pid=$(cat "$LOCK_FILE")
  if kill -0 "$pid" 2>/dev/null; then
    warn "另一个更新进程正在运行（PID $pid），跳过本次"
    exit 0
  fi
fi
echo $$ > "$LOCK_FILE"
trap 'rm -f "$LOCK_FILE"' EXIT

# ---------- 检测 OS ----------
OS="unknown"
[[ "$OSTYPE" == "darwin"* ]] && OS="macos"
[[ -f /etc/debian_version ]] && OS="debian"
[[ -f /etc/redhat-release ]] && OS="redhat"
grep -qi "synology" /etc/os-release 2>/dev/null && OS="synology"

sed_inplace() {
  if [[ "$OS" == "macos" ]]; then sed -i '' "$@"; else sed -i "$@"; fi
}

# ---------- 检查必要命令 ----------
command -v git    >/dev/null || error "未找到 git"
command -v docker >/dev/null || error "未找到 docker"
docker compose version >/dev/null 2>&1 || error "未找到 docker compose (v2)"

# ==========================================================================
# 1. 检查是否有新版本
# ==========================================================================
cd "$INSTALL_DIR"

info "检查远端更新..."
git fetch origin main --quiet

LOCAL_SHA=$(git rev-parse HEAD)
REMOTE_SHA=$(git rev-parse origin/main)
CURRENT_VERSION=$(git describe --tags --always 2>/dev/null || echo "${LOCAL_SHA:0:7}")
LATEST_VERSION=$(git describe --tags --always origin/main 2>/dev/null || echo "${REMOTE_SHA:0:7}")

if [[ "$LOCAL_SHA" == "$REMOTE_SHA" ]] && ! $FORCE; then
  success "已是最新版本（$CURRENT_VERSION），无需更新"
  exit 0
fi

if $CHECK_ONLY; then
  if [[ "$LOCAL_SHA" != "$REMOTE_SHA" ]]; then
    echo "发现新版本：$CURRENT_VERSION → $LATEST_VERSION"
    # 输出更新日志
    echo ""
    echo "更新内容："
    git log --oneline origin/main "^$LOCAL_SHA" | head -10
    exit 0
  else
    echo "已是最新版本（$CURRENT_VERSION）"
    exit 0
  fi
fi

# 输出将要更新的内容
CHANGELOG=$(git log --oneline origin/main "^$LOCAL_SHA" | head -10)
info "发现新版本：$CURRENT_VERSION → $LATEST_VERSION"
if [[ -n "$CHANGELOG" ]]; then
  echo "更新内容："
  echo "$CHANGELOG" | while read -r line; do echo "  • $line"; done
fi

# ==========================================================================
# 2. 更新前备份数据库
# ==========================================================================
info "备份数据库..."
BACKUP_KEEP="${UPDATE_BACKUP_KEEP:-7}"
BACKUP_DIR="$INSTALL_DIR/backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
mkdir -p "$BACKUP_DIR"

if docker compose ps backend 2>/dev/null | grep -q "running\|Up"; then
  docker compose exec -T backend sh -c \
    "sqlite3 /data/home_library.sqlite3 \".backup /backups/pre_update_${TIMESTAMP}.sqlite3\"" \
    2>/dev/null || true
  # 压缩
  BACKUP_FILE="$BACKUP_DIR/pre_update_${TIMESTAMP}.sqlite3"
  [[ -f "$BACKUP_FILE" ]] && gzip -f "$BACKUP_FILE" && \
    success "数据库已备份：${BACKUP_FILE}.gz"
fi

# 清理旧备份
find "$BACKUP_DIR" -name "pre_update_*.gz" -mtime "+$BACKUP_KEEP" -delete 2>/dev/null || true

# ==========================================================================
# 3. 拉取最新代码
# ==========================================================================
info "拉取最新代码..."
git pull origin main --ff-only || {
  warn "快进合并失败，尝试 rebase..."
  git pull origin main --rebase
}
success "代码已更新至 $LATEST_VERSION"

# ==========================================================================
# 4. 重建并重启服务（滚动更新，减少停机时间）
# ==========================================================================
info "重建镜像（后台构建，不中断现有服务）..."
docker compose build --quiet

info "重启服务..."
docker compose up -d --remove-orphans --wait --wait-timeout 120 2>/dev/null || \
  docker compose up -d --remove-orphans

# 等待健康检查
info "等待服务就绪..."
MAX_WAIT=120; ELAPSED=0
until docker compose ps backend 2>/dev/null | grep -q "healthy" || [[ $ELAPSED -ge $MAX_WAIT ]]; do
  sleep 3; ELAPSED=$((ELAPSED + 3)); printf "."
done
echo ""

if ! docker compose ps backend 2>/dev/null | grep -q "healthy"; then
  # 健康检查失败 - 回滚
  warn "服务启动失败，正在回滚到上一版本..."
  git checkout "$LOCAL_SHA" -- .
  docker compose build --quiet
  docker compose up -d --remove-orphans
  error "更新失败，已回滚到 $CURRENT_VERSION。请检查日志：docker compose logs backend"
fi

# ==========================================================================
# 5. 清理旧镜像
# ==========================================================================
docker image prune -f --filter "label=com.docker.compose.project=$(basename "$INSTALL_DIR")" \
  2>/dev/null || docker image prune -f 2>/dev/null || true

# ==========================================================================
# 6. 发送通知（可选）
# ==========================================================================
NOTIFY_URL="${UPDATE_NOTIFY_URL:-}"
if [[ -n "$NOTIFY_URL" ]]; then
  # 自动识别通知类型
  if [[ "$NOTIFY_URL" == *"qyapi.weixin.qq.com"* ]]; then
    # 企业微信机器人
    curl -s -X POST "$NOTIFY_URL" \
      -H "Content-Type: application/json" \
      -d "{\"msgtype\":\"text\",\"text\":{\"content\":\"家藏书库已更新\\n版本：${CURRENT_VERSION} → ${LATEST_VERSION}\\n时间：$(date '+%Y-%m-%d %H:%M')\\n\\n更新内容：\\n${CHANGELOG}\"}}" \
      >/dev/null 2>&1 || true
  elif [[ "$NOTIFY_URL" == *"oapi.dingtalk.com"* ]]; then
    # 钉钉机器人
    curl -s -X POST "$NOTIFY_URL" \
      -H "Content-Type: application/json" \
      -d "{\"msgtype\":\"text\",\"text\":{\"content\":\"家藏书库已更新 ${CURRENT_VERSION} → ${LATEST_VERSION}\"}}" \
      >/dev/null 2>&1 || true
  elif [[ "$NOTIFY_URL" == *"hooks.slack.com"* ]]; then
    # Slack
    curl -s -X POST "$NOTIFY_URL" \
      -H "Content-Type: application/json" \
      -d "{\"text\":\"✅ Home Library updated: ${CURRENT_VERSION} → ${LATEST_VERSION}\"}" \
      >/dev/null 2>&1 || true
  else
    # 通用 Webhook（POST JSON）
    curl -s -X POST "$NOTIFY_URL" \
      -H "Content-Type: application/json" \
      -d "{\"event\":\"update\",\"from\":\"${CURRENT_VERSION}\",\"to\":\"${LATEST_VERSION}\",\"time\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"}" \
      >/dev/null 2>&1 || true
  fi
  info "已发送更新通知"
fi

# ==========================================================================
# 完成
# ==========================================================================
success "✅ 更新完成：$CURRENT_VERSION → $LATEST_VERSION"
_log "INFO " "==================== 更新完成 ===================="
