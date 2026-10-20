#!/usr/bin/env bash
set -euo pipefail

root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
nginx_config="$root_dir/docker/nginx.conf"
frontend_client="$root_dir/frontend/src/api/client.ts"
backend_config="$root_dir/backend/app/core/config.py"

ai_location="$({
  awk '
    /location \/api\/ai\// { in_ai = 1 }
    in_ai { print }
    in_ai && /^    }$/ { exit }
  ' "$nginx_config"
})"

read_ts_value() {
  local key="$1"
  sed -nE "s/^[[:space:]]*$key:[[:space:]]*([0-9_]+),$/\1/p" "$frontend_client" | tr -d '_'
}

read_nginx_seconds() {
  local directive="$1"
  sed -nE "s/^[[:space:]]*$directive[[:space:]]+([0-9]+)s;$/\1/p" <<<"$ai_location"
}

ai_health_ms="$(read_ts_value aiHealth)"
ai_generation_ms="$(read_ts_value aiGeneration)"
backend_read_seconds="$({
  awk '
    /ollama_read_timeout_seconds: float = Field\(/ { in_field = 1 }
    in_field && /default=/ {
      line = $0
      sub(/^.*default=/, "", line)
      sub(/,.*/, "", line)
      print line
      exit
    }
  ' "$backend_config"
})"
nginx_send_seconds="$(read_nginx_seconds proxy_send_timeout)"
nginx_read_seconds="$(read_nginx_seconds proxy_read_timeout)"

for value in \
  "$ai_health_ms" \
  "$ai_generation_ms" \
  "$backend_read_seconds" \
  "$nginx_send_seconds" \
  "$nginx_read_seconds"; do
  [[ "$value" =~ ^[0-9]+([.][0-9]+)?$ ]]
done

awk -v backend="$backend_read_seconds" \
    -v health_ms="$ai_health_ms" \
    -v generation_ms="$ai_generation_ms" \
    -v send="$nginx_send_seconds" \
    -v read="$nginx_read_seconds" '
  BEGIN {
    health = health_ms / 1000
    generation = generation_ms / 1000
    if (!(backend < health && backend < generation && health < send && health < read && generation < send && generation < read)) {
      exit 1
    }
  }
'

printf 'AI timeout contract passed: backend=%ss frontend-health=%ss frontend-generation=%ss nginx-send=%ss nginx-read=%ss\n' \
  "$backend_read_seconds" \
  "$((ai_health_ms / 1000))" \
  "$((ai_generation_ms / 1000))" \
  "$nginx_send_seconds" \
  "$nginx_read_seconds"
