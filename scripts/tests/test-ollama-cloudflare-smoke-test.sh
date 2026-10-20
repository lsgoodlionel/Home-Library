#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
script="${repo_root}/scripts/ollama-cloudflare-smoke-test.sh"
tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT

fake_bin="${tmp_dir}/bin"
mkdir -p "$fake_bin"
cat > "${fake_bin}/curl" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
printf '%q ' "$@" >> "$FAKE_CURL_ARGS"
printf '\n' >> "$FAKE_CURL_ARGS"
if [[ " $* " == *" --config - "* ]]; then
  cat >> "$FAKE_CURL_STDIN"
fi
printf '200'
EOF
chmod +x "${fake_bin}/curl"

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

run_case() {
  local name="$1"
  local base_url="$2"
  local trusted_url="$3"
  local expected_status="$4"
  local expected_calls="$5"
  local output_file="${tmp_dir}/${name}.output"
  local args_file="${tmp_dir}/${name}.args"
  local stdin_file="${tmp_dir}/${name}.stdin"
  : > "$args_file"
  : > "$stdin_file"

  set +e
  PATH="${fake_bin}:$PATH" \
    FAKE_CURL_ARGS="$args_file" \
    FAKE_CURL_STDIN="$stdin_file" \
    OLLAMA_BASE_URL="$base_url" \
    OLLAMA_TRUSTED_BASE_URL="$trusted_url" \
    OLLAMA_CF_ACCESS_CLIENT_ID="test-client-id" \
    OLLAMA_CF_ACCESS_CLIENT_SECRET="test-client-secret" \
    bash "$script" > "$output_file" 2>&1
  local status=$?
  set -e

  [[ "$status" -eq "$expected_status" ]] || fail "$name exit=$status expected=$expected_status"
  local calls
  calls="$(wc -l < "$args_file" | tr -d ' ')"
  [[ "$calls" -eq "$expected_calls" ]] || fail "$name curl_calls=$calls expected=$expected_calls"
  ! grep -q 'test-client-secret' "$args_file" || fail "$name exposed secret in curl argv"
  ! grep -q 'test-client-secret' "$output_file" || fail "$name exposed secret in output"

  if [[ "$expected_calls" -eq 0 ]]; then
    [[ ! -s "$stdin_file" ]] || fail "$name sent credentials without a trusted origin"
  else
    grep -q 'test-client-secret' "$stdin_file" || fail "$name omitted credentials for trusted origin"
  fi
}

run_case trusted_path \
  'https://openclaw.lsgood.cn/ollama' \
  'https://openclaw.lsgood.cn' \
  0 3
run_case third_party \
  'https://example.com' \
  'https://openclaw.lsgood.cn' \
  2 0
run_case port_mismatch \
  'https://openclaw.lsgood.cn:8443' \
  'https://openclaw.lsgood.cn' \
  2 0
run_case scheme_mismatch \
  'http://openclaw.lsgood.cn' \
  'https://openclaw.lsgood.cn' \
  2 0
run_case default_https_port \
  'https://openclaw.lsgood.cn:443/api-root' \
  'https://openclaw.lsgood.cn' \
  0 3
run_case default_http_port \
  'http://localhost:80' \
  'http://localhost' \
  0 3
run_case ipv6_match \
  'https://[2001:db8::1]:443/ollama' \
  'https://[2001:db8::1]' \
  0 3
run_case ipv6_mismatch \
  'https://[2001:db8::2]' \
  'https://[2001:db8::1]' \
  2 0
run_case ipv6_invalid \
  'https://[2001:db8::not-hex]' \
  'https://[2001:db8::not-hex]' \
  2 0
run_case userinfo \
  'https://user:password@openclaw.lsgood.cn' \
  'https://openclaw.lsgood.cn' \
  2 0
run_case control_character \
  $'https://openclaw.lsgood.cn\n.example.com' \
  'https://openclaw.lsgood.cn' \
  2 0

echo "ollama cloudflare smoke origin tests passed"
