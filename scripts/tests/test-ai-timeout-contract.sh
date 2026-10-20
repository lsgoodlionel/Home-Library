#!/usr/bin/env bash
set -euo pipefail

root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
nginx_config="$root_dir/docker/nginx.conf"

ai_location="$({
  awk '
    /location \/api\/ai\// { in_ai = 1 }
    in_ai { print }
    in_ai && /^    }$/ { exit }
  ' "$nginx_config"
})"

grep -q 'proxy_send_timeout 300s;' <<<"$ai_location"
grep -q 'proxy_read_timeout 300s;' <<<"$ai_location"

printf 'AI timeout contract passed\n'
