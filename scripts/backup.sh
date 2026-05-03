#!/usr/bin/env sh
set -eu

BACKUP_DIR="${BACKUP_DIR:-/backups}"
UPLOAD_DIR="${UPLOAD_DIR:-/uploads}"
KEEP_DAYS="${KEEP_DAYS:-7}"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"

mkdir -p "$BACKUP_DIR"

DB_PATH="${DATABASE_PATH:-}"
if [ -z "$DB_PATH" ] && [ -n "${DATABASE_URL:-}" ]; then
  case "$DATABASE_URL" in
    sqlite:////*) DB_PATH="/${DATABASE_URL#sqlite:////}" ;;
    sqlite:///*) DB_PATH="${DATABASE_URL#sqlite:///}" ;;
  esac
fi
DB_PATH="${DB_PATH:-/data/home_library.sqlite3}"

if [ -f "$DB_PATH" ]; then
  DB_BACKUP="$BACKUP_DIR/home_library_${TIMESTAMP}.sqlite3"
  if command -v sqlite3 >/dev/null 2>&1; then
    sqlite3 "$DB_PATH" ".backup '$DB_BACKUP'"
  else
    cp "$DB_PATH" "$DB_BACKUP"
  fi
  gzip -f "$DB_BACKUP"
  echo "Database backup written: ${DB_BACKUP}.gz"
else
  echo "Database file not found, skipped: $DB_PATH"
fi

if [ -d "$UPLOAD_DIR" ]; then
  UPLOAD_BACKUP="$BACKUP_DIR/uploads_${TIMESTAMP}.tar.gz"
  tar -czf "$UPLOAD_BACKUP" -C "$UPLOAD_DIR" .
  echo "Uploads backup written: $UPLOAD_BACKUP"
else
  echo "Upload directory not found, skipped: $UPLOAD_DIR"
fi

find "$BACKUP_DIR" -type f -mtime +"$KEEP_DAYS" -name "*.gz" -delete
echo "Old backups older than ${KEEP_DAYS} days removed."
