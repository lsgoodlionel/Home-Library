#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT

cp "$repo_root/docker-compose.prod.yml" "$tmp_dir/docker-compose.prod.yml"
: > "$tmp_dir/.env"

rendered="$tmp_dir/rendered.yml"
UPGRADE_PASSWORD="compose-security-sentinel" \
TRUSTED_HTTPS_PROXY_IP="192.0.2.19" \
HOME_LIBRARY_DOCKER_SUBNET="172.30.81.0/24" \
HOME_LIBRARY_FRONTEND_IP="172.30.81.3" \
  docker compose -f "$tmp_dir/docker-compose.prod.yml" config --format json > "$rendered"

python3 - "$rendered" <<'PY'
import json
import sys
from pathlib import Path

config = json.loads(Path(sys.argv[1]).read_text())
backend = config["services"]["backend"]
frontend = config["services"]["frontend"]
assert backend["environment"]["UPGRADE_PASSWORD"] == "compose-security-sentinel"
assert backend["environment"]["SERVER_CONFIG_TRUSTED_PROXY_IPS"] == "172.30.81.3"
assert frontend["environment"]["TRUSTED_HTTPS_PROXY_IP"] == "192.0.2.19"
assert frontend["networks"]["default"]["ipv4_address"] == "172.30.81.3"
assert config["networks"]["default"]["ipam"]["config"][0]["subnet"] == "172.30.81.0/24"
PY

nginx_config="$repo_root/docker/nginx.conf"
grep -Fq '"${TRUSTED_HTTPS_PROXY_IP}:https" https;' "$nginx_config" || {
  echo "FAIL: Nginx must only preserve HTTPS from the configured direct proxy" >&2
  exit 1
}
[[ "$(grep -Fc 'proxy_set_header X-Forwarded-Proto $trusted_forwarded_proto;' "$nginx_config")" -eq 2 ]] || {
  echo "FAIL: Nginx must pass its sanitized protocol value to the backend" >&2
  exit 1
}
grep -Fq 'COPY docker/nginx.conf /etc/nginx/templates/default.conf.template' \
  "$repo_root/docker/Dockerfile.frontend" || {
  echo "FAIL: the frontend image must expand the trusted proxy IP at startup" >&2
  exit 1
}

echo "production Compose security environment tests passed"
