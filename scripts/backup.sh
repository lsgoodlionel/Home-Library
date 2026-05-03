#!/usr/bin/env bash
# backup.sh — 备份 SQLite 数据库和上传文件到 backups/ 目录
#
# 用法（在项目根目录执行）：
#   ./scripts/backup.sh
#
# 使用 Docker Compose 执行：
#   docker compose exec backend /app/scripts/backup.sh
#
# 备份文件格式：
#   backups/db_YYYYMMDD_HHMMSS.sqlite3
#   backups/uploads_YYYYMMDD_HHMMSS.tar.gz
#
# 自动保留最近 7 天的备份（KEEP_DAYS 可覆盖）。

set -euo pipefail

# ── 配置 ──────────────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

DB_PATH="${DATABASE_URL:-}"
# 从 DATABASE_URL 中提取文件路径（sqlite:///./xxx 或 sqlite:////absolute/path）
if [[ "$DB_PATH" == sqlite:///* ]]; then
  DB_PATH="${DB_PATH#sqlite:///}"
fi
if [[ -z "$DB_PATH" ]]; then
  # 默认位置（Docker 内 /data/，本地开发 backend/）
  if [[ -f "/data/home_library.sqlite3" ]]; then
    DB_PATH="/data/home_library.sqlite3"
  else
    DB_PATH="${PROJECT_ROOT}/backend/home_library.sqlite3"
  fi
fi

UPLOADS_DIR="${UPLOAD_DIR:-${PROJECT_ROOT}/uploads}"
BACKUP_DIR="${BACKUP_ROOT:-${PROJECT_ROOT}/backups}"
KEEP_DAYS="${KEEP_DAYS:-7}"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"

# ── 准备 ──────────────────────────────────────────────────────────────────────
mkdir -p "$BACKUP_DIR"

echo "[backup] 时间戳: $TIMESTAMP"
echo "[backup] 数据库: $DB_PATH"
echo "[backup] 上传目录: $UPLOADS_DIR"
echo "[backup] 备份目录: $BACKUP_DIR"

# ── 备份数据库 ────────────────────────────────────────────────────────────────
if [[ -f "$DB_PATH" ]]; then
  DB_BACKUP="$BACKUP_DIR/db_${TIMESTAMP}.sqlite3"
  # 使用 SQLite 在线备份 API（避免文件锁问题）
  if command -v sqlite3 &>/dev/null; then
    sqlite3 "$DB_PATH" ".backup '$DB_BACKUP'"
  else
    cp "$DB_PATH" "$DB_BACKUP"
  fi
  echo "[backup] ✓ 数据库已备份 → $(basename "$DB_BACKUP")"
else
  echo "[backup] ⚠ 数据库文件不存在，跳过: $DB_PATH"
fi

# ── 备份上传文件 ──────────────────────────────────────────────────────────────
if [[ -d "$UPLOADS_DIR" ]] && [[ -n "$(ls -A "$UPLOADS_DIR" 2>/dev/null)" ]]; then
  UPLOADS_BACKUP="$BACKUP_DIR/uploads_${TIMESTAMP}.tar.gz"
  tar -czf "$UPLOADS_BACKUP" -C "$(dirname "$UPLOADS_DIR")" "$(basename "$UPLOADS_DIR")"
  echo "[backup] ✓ 上传文件已备份 → $(basename "$UPLOADS_BACKUP")"
else
  echo "[backup] ⚠ 上传目录为空或不存在，跳过: $UPLOADS_DIR"
fi

# ── 清理旧备份 ────────────────────────────────────────────────────────────────
echo "[backup] 清理 ${KEEP_DAYS} 天前的旧备份..."
find "$BACKUP_DIR" -maxdepth 1 \( -name "db_*.sqlite3" -o -name "uploads_*.tar.gz" \) \
  -mtime "+${KEEP_DAYS}" -delete -print | sed 's/^/[backup]   删除 /'

echo "[backup] 完成。"
