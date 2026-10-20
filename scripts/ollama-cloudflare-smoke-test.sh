#!/usr/bin/env bash
set -euo pipefail

base_url="${OLLAMA_BASE_URL:-https://openclaw.lsgood.cn}"
base_url="${base_url%/}"
connect_timeout="${OLLAMA_CONNECT_TIMEOUT_SECONDS:-20}"
read_timeout="${OLLAMA_READ_TIMEOUT_SECONDS:-180}"
verify_tls="${OLLAMA_VERIFY_TLS:-true}"
client_id="${OLLAMA_CF_ACCESS_CLIENT_ID:-}"
client_secret="${OLLAMA_CF_ACCESS_CLIENT_SECRET:-}"

if [[ -z "$base_url" ]]; then
  echo "错误：OLLAMA_BASE_URL 不能为空。" >&2
  exit 2
fi

if [[ -n "$client_id" && -z "$client_secret" ]] || [[ -z "$client_id" && -n "$client_secret" ]]; then
  echo "错误：Cloudflare Access Client ID 和 Secret 必须同时配置。" >&2
  exit 2
fi

curl_args=(
  --silent
  --show-error
  --output /dev/null
  --connect-timeout "$connect_timeout"
  --max-time "$read_timeout"
)

if [[ "$verify_tls" == "false" ]]; then
  curl_args+=(--insecure)
fi

curl_status() {
  local endpoint="$1"
  if [[ -n "$client_id" ]]; then
    curl "${curl_args[@]}" --config - --write-out '%{http_code}' "${base_url}${endpoint}" <<EOF
header = "CF-Access-Client-Id: ${client_id}"
header = "CF-Access-Client-Secret: ${client_secret}"
EOF
  else
    curl "${curl_args[@]}" --write-out '%{http_code}' "${base_url}${endpoint}"
  fi
}

for endpoint in /api/version /api/tags /api/ps; do
  http_status="$(curl_status "$endpoint" || true)"
  if [[ "$http_status" != "200" ]]; then
    echo "失败：${endpoint} 返回 HTTP ${http_status:-000}。" >&2
    exit 1
  fi
  echo "通过：${endpoint}"
done

echo "Ollama 只读远程烟雾测试通过。"
