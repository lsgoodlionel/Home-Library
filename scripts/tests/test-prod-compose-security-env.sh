#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT

cp "$repo_root/docker-compose.prod.yml" "$tmp_dir/docker-compose.prod.yml"
cp "$repo_root/docker-compose.yml" "$tmp_dir/docker-compose.yml"
: > "$tmp_dir/.env"

rendered="$tmp_dir/rendered.yml"
UPGRADE_PASSWORD="compose-security-sentinel" \
  docker compose -f "$tmp_dir/docker-compose.prod.yml" config > "$rendered"

grep -Fq 'UPGRADE_PASSWORD: compose-security-sentinel' "$rendered" || {
  echo "FAIL: production Compose does not pass UPGRADE_PASSWORD to backend" >&2
  exit 1
}

grep -Fq 'AI_PROVIDER_ALLOWED_PRIVATE_ORIGINS: ""' "$rendered" || {
  echo "FAIL: production Compose does not pass an explicit default-empty provider allowlist" >&2
  exit 1
}

rendered_dev="$tmp_dir/rendered-dev.yml"
docker compose -f "$tmp_dir/docker-compose.yml" config > "$rendered_dev"
grep -Fq 'AI_PROVIDER_ALLOWED_PRIVATE_ORIGINS: ""' "$rendered_dev" || {
  echo "FAIL: development Compose does not pass an explicit default-empty provider allowlist" >&2
  exit 1
}

echo "development and production Compose security environment tests passed"
