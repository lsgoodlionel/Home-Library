#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
deploy_script="${repo_root}/scripts/deploy.sh"
tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

git init --bare "$tmp_dir/remote.git" >/dev/null
git -C "$tmp_dir/remote.git" symbolic-ref HEAD refs/heads/main
git init -b main "$tmp_dir/source" >/dev/null
git -C "$tmp_dir/source" config user.name "Home Library Test"
git -C "$tmp_dir/source" config user.email "test@example.invalid"

printf 'services: {}\n' > "$tmp_dir/source/docker-compose.prod.yml"
cat > "$tmp_dir/source/.env.example" <<'ENV'
HTTP_PORT=80
APP_SECRET_KEY=replace-me
INITIAL_ADMIN_USERNAME=admin
INITIAL_ADMIN_PASSWORD=replace-me
CORS_ORIGINS=http://localhost
ENV
git -C "$tmp_dir/source" add docker-compose.prod.yml .env.example
git -C "$tmp_dir/source" commit -m baseline >/dev/null
baseline_sha="$(git -C "$tmp_dir/source" rev-parse HEAD)"
git -C "$tmp_dir/source" remote add origin "$tmp_dir/remote.git"
git -C "$tmp_dir/source" push -u origin main >/dev/null

mkdir -p "$tmp_dir/home"
git clone "$tmp_dir/remote.git" "$tmp_dir/home/home-library" >/dev/null
git -C "$tmp_dir/home/home-library" config user.name "Home Library Test"
git -C "$tmp_dir/home/home-library" config user.email "test@example.invalid"

printf 'newer application code\n' > "$tmp_dir/source/application.txt"
git -C "$tmp_dir/source" add application.txt
git -C "$tmp_dir/source" commit -m newer >/dev/null
newer_sha="$(git -C "$tmp_dir/source" rev-parse HEAD)"
git -C "$tmp_dir/source" push origin main >/dev/null
git -C "$tmp_dir/source" tag v0.1.0
git -C "$tmp_dir/source" push origin v0.1.0 >/dev/null
git -C "$tmp_dir/home/home-library" pull --ff-only >/dev/null
git -C "$tmp_dir/home/home-library" fetch origin tag v0.1.0 >/dev/null

git -C "$tmp_dir/source" reset --hard "$baseline_sha" >/dev/null
printf 'rollback deploy hotfix\n' > "$tmp_dir/source/deployer.txt"
mkdir -p "$tmp_dir/source/scripts"
cp "$repo_root/scripts/update.sh" "$tmp_dir/source/scripts/update.sh"
git -C "$tmp_dir/source" add deployer.txt scripts/update.sh
git -C "$tmp_dir/source" commit -m rollback-deployer >/dev/null
rollback_sha="$(git -C "$tmp_dir/source" rev-parse HEAD)"
git -C "$tmp_dir/source" push --force origin main >/dev/null
git -C "$tmp_dir/source" tag -f v0.1.0 >/dev/null
git -C "$tmp_dir/source" push --force origin v0.1.0 >/dev/null

mkdir -p "$tmp_dir/bin"
cat > "$tmp_dir/bin/docker" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$*" >> "$DOCKER_LOG"
case "$*" in
  *"ps backend"*) printf 'backend running healthy\n' ;;
esac
SH
chmod +x "$tmp_dir/bin/docker"

cat > "$tmp_dir/bin/curl" <<SH
#!/usr/bin/env bash
cat "$repo_root/scripts/update.sh"
SH
chmod +x "$tmp_dir/bin/curl"

cat > "$tmp_dir/home/home-library/.env" <<'ENV'
HTTP_PORT=127.0.0.1:80
APP_SECRET_KEY=existing-secret-must-survive
INITIAL_ADMIN_USERNAME=existing-admin
INITIAL_ADMIN_PASSWORD=existing-password
CORS_ORIGINS=https://library.example.invalid
ENV
cp "$tmp_dir/home/home-library/.env" "$tmp_dir/original.env"

HOME="$tmp_dir/home" \
  PATH="$tmp_dir/bin:/usr/bin:/bin" \
  DOCKER_LOG="$tmp_dir/docker.log" \
  bash <(cat "$deploy_script") -d >/dev/null

actual_sha="$(git -C "$tmp_dir/home/home-library" rev-parse HEAD)"
[[ "$actual_sha" == "$rollback_sha" ]] \
  || fail "installed checkout stayed at $actual_sha instead of syncing to $rollback_sha"

git -C "$tmp_dir/home/home-library" for-each-ref \
  --format='%(objectname)' refs/heads/backup/home-library-update \
  | grep -Fqx "$newer_sha" \
  || fail "rewound server commit was not preserved on a backup branch"

grep -Fq "compose -f $tmp_dir/home/home-library/docker-compose.prod.yml pull" "$tmp_dir/docker.log" \
  || fail "deployment did not pull the rollback image after synchronizing code"

cmp -s "$tmp_dir/original.env" "$tmp_dir/home/home-library/.env" \
  || fail "rerunning deploy.sh changed the existing server .env"

grep -Fq 'sqlite3 /data/home_library.sqlite3' "$tmp_dir/docker.log" \
  || fail "rerunning deploy.sh did not use the database-backed update path"

echo "history rewind deploy tests passed"
