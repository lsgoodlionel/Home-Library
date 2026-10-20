#!/usr/bin/env bash
set -euo pipefail

base_url="${OLLAMA_BASE_URL:-https://openclaw.lsgood.cn}"
base_url="${base_url%/}"
trusted_base_url="${OLLAMA_TRUSTED_BASE_URL:-https://openclaw.lsgood.cn}"
connect_timeout="${OLLAMA_CONNECT_TIMEOUT_SECONDS:-20}"
read_timeout="${OLLAMA_READ_TIMEOUT_SECONDS:-180}"
verify_tls="${OLLAMA_VERIFY_TLS:-true}"
client_id="${OLLAMA_CF_ACCESS_CLIENT_ID:-}"
client_secret="${OLLAMA_CF_ACCESS_CLIENT_SECRET:-}"

if [[ -z "$base_url" ]]; then
  echo "错误：OLLAMA_BASE_URL 不能为空。" >&2
  exit 2
fi

normalize_origin() {
  python3 - "$1" <<'PY'
import ipaddress
import re
import sys
from urllib.parse import urlsplit

raw = sys.argv[1]
if not raw or any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in raw):
    raise SystemExit(2)

try:
    parsed = urlsplit(raw)
    scheme = parsed.scheme.lower()
    hostname = parsed.hostname
    port = parsed.port
except ValueError:
    raise SystemExit(2)

if scheme not in {"http", "https"} or not parsed.netloc or hostname is None:
    raise SystemExit(2)
if parsed.username is not None or parsed.password is not None or parsed.netloc.endswith(":"):
    raise SystemExit(2)

hostname = hostname.lower()
if ":" in hostname:
    try:
        ipaddress.IPv6Address(hostname)
    except ValueError:
        raise SystemExit(2)
    normalized_host = f"[{hostname}]"
else:
    try:
        normalized_host = hostname.encode("idna").decode("ascii")
    except UnicodeError:
        raise SystemExit(2)
    dns_name = re.fullmatch(
        r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)*",
        normalized_host,
    )
    if dns_name is None or len(normalized_host) > 253:
        raise SystemExit(2)

default_port = 443 if scheme == "https" else 80
if port is not None and not 1 <= port <= 65535:
    raise SystemExit(2)
port_suffix = "" if port is None or port == default_port else f":{port}"
print(f"{scheme}://{normalized_host}{port_suffix}")
PY
}

if ! base_origin="$(normalize_origin "$base_url")"; then
  echo "错误：OLLAMA_BASE_URL 不是有效的 HTTP(S) 地址。" >&2
  exit 2
fi
if ! trusted_origin="$(normalize_origin "$trusted_base_url")"; then
  echo "错误：OLLAMA_TRUSTED_BASE_URL 不是有效的 HTTP(S) 地址。" >&2
  exit 2
fi
if [[ "$base_origin" != "$trusted_origin" ]]; then
  echo "错误：OLLAMA_BASE_URL 与受信任地址的 Origin 不一致，已拒绝请求。" >&2
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
