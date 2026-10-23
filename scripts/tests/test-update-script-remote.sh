#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
update_script="${repo_root}/scripts/update.sh"
tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

mkdir -p "$tmp_dir/bin" "$tmp_dir/home/home-library" "$tmp_dir/custom-install"

cat > "$tmp_dir/bin/docker" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$*" >> "$DOCKER_LOG"
case "$*" in
  *"ps backend"*) printf 'backend running healthy\n' ;;
esac
exit 0
SH
chmod +x "$tmp_dir/bin/docker"

run_remote_update() {
  HOME="$tmp_dir/home" \
    PATH="$tmp_dir/bin:/usr/bin:/bin" \
    DOCKER_LOG="$tmp_dir/docker.log" \
    bash <(cat "$update_script") "$@"
}

: > "$tmp_dir/docker.log"
run_remote_update --check >/dev/null
grep -Fqx \
  "compose -f $tmp_dir/home/home-library/docker-compose.prod.yml ps backend" \
  "$tmp_dir/docker.log" \
  || fail "remote execution did not default to ~/home-library"

: > "$tmp_dir/docker.log"
run_remote_update --install-dir "$tmp_dir/custom-install" --check >/dev/null
grep -Fqx \
  "compose -f $tmp_dir/custom-install/docker-compose.prod.yml ps backend" \
  "$tmp_dir/docker.log" \
  || fail "--install-dir did not select the requested installation"

if run_remote_update --install-dir >/dev/null 2>&1; then
  fail "missing --install-dir value must be rejected"
fi

if run_remote_update --install-dir "$tmp_dir/custom-install" --source >/dev/null 2>&1; then
  fail "source updates must reject an installation without Git metadata"
fi

echo "remote update command tests passed"
