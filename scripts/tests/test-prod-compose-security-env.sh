#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT

cp "$repo_root/docker-compose.prod.yml" "$tmp_dir/docker-compose.prod.yml"
: > "$tmp_dir/.env"

rendered="$tmp_dir/rendered.yml"
UPGRADE_PASSWORD="compose-security-sentinel" \
  docker compose -f "$tmp_dir/docker-compose.prod.yml" config > "$rendered"

grep -Fq 'UPGRADE_PASSWORD: compose-security-sentinel' "$rendered" || {
  echo "FAIL: production Compose does not pass UPGRADE_PASSWORD to backend" >&2
  exit 1
}

echo "production Compose security environment tests passed"
