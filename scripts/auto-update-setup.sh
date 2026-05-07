#!/usr/bin/env bash
# =============================================================================
# 家藏书库 Home Library — 自动更新配置脚本
# 在目标服务器上执行一次，之后自动定期检查并更新
#
# 用法：
#   bash auto-update-setup.sh              # 默认每天凌晨 3 点更新
#   bash auto-update-setup.sh --cron      # 强制使用 cron（不用 systemd）
#   bash auto-update-setup.sh --remove    # 移除自动更新
#   bash auto-update-setup.sh --interval "0 3 * * *"  # 自定义 cron 表达式
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="$(dirname "$SCRIPT_DIR")"
UPDATE_SCRIPT="$SCRIPT_DIR/update.sh"
SERVICE_NAME="home-library-update"
DEFAULT_CRON="0 3 * * *"   # 每天 03:00
FORCE_CRON=false
REMOVE=false
CRON_EXPR="$DEFAULT_CRON"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
info()    { echo -e "${BLUE}[INFO]${NC}  $*"; }
success() { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

for arg in "$@"; do
  case $arg in
    --cron)   FORCE_CRON=true ;;
    --remove) REMOVE=true ;;
    --interval) CRON_EXPR="${2:-$DEFAULT_CRON}"; shift ;;
  esac
done

chmod +x "$UPDATE_SCRIPT"

# ============================================================
# 移除自动更新
# ============================================================
if $REMOVE; then
  info "移除自动更新配置..."

  # 移除 systemd timer
  if systemctl list-timers "$SERVICE_NAME.timer" 2>/dev/null | grep -q "$SERVICE_NAME"; then
    sudo systemctl stop "$SERVICE_NAME.timer" 2>/dev/null || true
    sudo systemctl disable "$SERVICE_NAME.timer" 2>/dev/null || true
    sudo rm -f "/etc/systemd/system/${SERVICE_NAME}.timer"
    sudo rm -f "/etc/systemd/system/${SERVICE_NAME}.service"
    sudo systemctl daemon-reload
    success "已移除 systemd timer"
  fi

  # 移除 cron
  crontab -l 2>/dev/null | grep -v "home-library" | crontab - 2>/dev/null || true
  success "已移除 cron job"

  # 移除 launchd (macOS)
  PLIST="$HOME/Library/LaunchAgents/com.home-library.update.plist"
  if [[ -f "$PLIST" ]]; then
    launchctl unload "$PLIST" 2>/dev/null || true
    rm -f "$PLIST"
    success "已移除 macOS LaunchAgent"
  fi

  success "自动更新已停用"
  exit 0
fi

echo ""
echo "=========================================================="
echo "   家藏书库 — 自动更新配置"
echo "=========================================================="
echo ""
echo "  更新频率：$CRON_EXPR（cron 格式）"
echo "  更新脚本：$UPDATE_SCRIPT"
echo ""

# ============================================================
# macOS：使用 launchd
# ============================================================
if [[ "$OSTYPE" == "darwin"* ]]; then
  info "配置 macOS LaunchAgent..."

  # 将 cron 转为 launchd StartCalendarInterval（简化：支持每天固定时间）
  HOUR=$(echo "$CRON_EXPR" | awk '{print $2}')
  MINUTE=$(echo "$CRON_EXPR" | awk '{print $1}')
  [[ "$HOUR" == "*" ]] && HOUR=3
  [[ "$MINUTE" == "*" ]] && MINUTE=0

  PLIST_DIR="$HOME/Library/LaunchAgents"
  PLIST="$PLIST_DIR/com.home-library.update.plist"
  mkdir -p "$PLIST_DIR"

  cat > "$PLIST" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.home-library.update</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>${UPDATE_SCRIPT}</string>
    <string>--auto</string>
  </array>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key>   <integer>${HOUR}</integer>
    <key>Minute</key> <integer>${MINUTE}</integer>
  </dict>
  <key>StandardOutPath</key>
  <string>${INSTALL_DIR}/logs/update.log</string>
  <key>StandardErrorPath</key>
  <string>${INSTALL_DIR}/logs/update.log</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key>
    <string>/usr/local/bin:/usr/bin:/bin:/opt/homebrew/bin</string>
  </dict>
  <key>RunAtLoad</key>
  <false/>
</dict>
</plist>
EOF

  launchctl unload "$PLIST" 2>/dev/null || true
  launchctl load "$PLIST"
  success "LaunchAgent 已配置（每天 ${HOUR}:$(printf '%02d' $MINUTE) 自动检查更新）"
  echo ""
  echo "  管理命令："
  echo "    立即执行：launchctl start com.home-library.update"
  echo "    查看状态：launchctl list com.home-library.update"
  echo "    停止：    bash $SCRIPT_DIR/auto-update-setup.sh --remove"
  exit 0
fi

# ============================================================
# Linux：优先用 systemd timer，降级到 cron
# ============================================================
USE_SYSTEMD=false
if ! $FORCE_CRON && command -v systemctl &>/dev/null && \
   systemctl is-system-running 2>/dev/null | grep -qE "running|degraded"; then
  USE_SYSTEMD=true
fi

if $USE_SYSTEMD; then
  # ---------- systemd timer ----------
  info "配置 systemd timer..."

  # 将 cron 表达式转为 systemd OnCalendar
  # 支持常见格式：每天 / 每小时 / 自定义
  HOUR=$(echo "$CRON_EXPR"   | awk '{print $2}')
  MINUTE=$(echo "$CRON_EXPR" | awk '{print $1}')
  [[ "$HOUR" == "*" ]]   && ON_CALENDAR="*:${MINUTE}:00" || ON_CALENDAR="*-*-* ${HOUR}:${MINUTE}:00"

  sudo tee "/etc/systemd/system/${SERVICE_NAME}.service" > /dev/null << EOF
[Unit]
Description=Home Library Auto Update
After=network-online.target docker.service
Wants=network-online.target

[Service]
Type=oneshot
User=$(whoami)
WorkingDirectory=${INSTALL_DIR}
ExecStart=/bin/bash ${UPDATE_SCRIPT} --auto
StandardOutput=append:${INSTALL_DIR}/logs/update.log
StandardError=append:${INSTALL_DIR}/logs/update.log
Environment=PATH=/usr/local/bin:/usr/bin:/bin
EOF

  sudo tee "/etc/systemd/system/${SERVICE_NAME}.timer" > /dev/null << EOF
[Unit]
Description=Home Library Auto Update Timer
Requires=${SERVICE_NAME}.service

[Timer]
OnCalendar=${ON_CALENDAR}
RandomizedDelaySec=600
Persistent=true

[Install]
WantedBy=timers.target
EOF

  mkdir -p "$INSTALL_DIR/logs"
  sudo systemctl daemon-reload
  sudo systemctl enable "${SERVICE_NAME}.timer"
  sudo systemctl start  "${SERVICE_NAME}.timer"

  success "systemd timer 已配置（$ON_CALENDAR）"
  echo ""
  echo "  管理命令："
  echo "    立即更新：sudo systemctl start ${SERVICE_NAME}.service"
  echo "    查看状态：sudo systemctl status ${SERVICE_NAME}.timer"
  echo "    查看日志：sudo journalctl -u ${SERVICE_NAME}.service -f"
  echo "    停止自动：bash $SCRIPT_DIR/auto-update-setup.sh --remove"

else
  # ---------- cron ----------
  info "配置 cron job..."
  mkdir -p "$INSTALL_DIR/logs"

  # 获取 docker 完整路径
  DOCKER_PATH=$(command -v docker)
  # PATH 保证 cron 环境能找到 git/docker
  CRON_PATH="/usr/local/bin:/usr/bin:/bin:$(dirname "$DOCKER_PATH")"
  CRON_LINE="$CRON_EXPR PATH=$CRON_PATH /bin/bash $UPDATE_SCRIPT --auto >> $INSTALL_DIR/logs/update.log 2>&1"
  CRON_MARK="# home-library-auto-update"

  # 移除旧配置再写入
  (crontab -l 2>/dev/null | grep -v "home-library" || true
   echo "$CRON_MARK"
   echo "$CRON_LINE") | crontab -

  success "cron job 已配置（$CRON_EXPR）"
  echo ""
  echo "  管理命令："
  echo "    立即更新：bash $UPDATE_SCRIPT"
  echo "    查看任务：crontab -l"
  echo "    查看日志：tail -f $INSTALL_DIR/logs/update.log"
  echo "    停止自动：bash $SCRIPT_DIR/auto-update-setup.sh --remove"
fi

echo ""
info "立即执行一次测试（仅检查，不更新）..."
bash "$UPDATE_SCRIPT" --check || true
echo ""
success "自动更新配置完成！"
