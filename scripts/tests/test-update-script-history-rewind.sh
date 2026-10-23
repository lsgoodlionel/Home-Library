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

git init --bare "$tmp_dir/remote.git" >/dev/null
git -C "$tmp_dir/remote.git" symbolic-ref HEAD refs/heads/main
git init -b main "$tmp_dir/source" >/dev/null
git -C "$tmp_dir/source" config user.name "Home Library Test"
git -C "$tmp_dir/source" config user.email "test@example.invalid"

printf 'services: {}\n' > "$tmp_dir/source/docker-compose.prod.yml"
git -C "$tmp_dir/source" add docker-compose.prod.yml
git -C "$tmp_dir/source" commit -m baseline >/dev/null
baseline_sha="$(git -C "$tmp_dir/source" rev-parse HEAD)"
git -C "$tmp_dir/source" remote add origin "$tmp_dir/remote.git"
git -C "$tmp_dir/source" push -u origin main >/dev/null

git clone "$tmp_dir/remote.git" "$tmp_dir/install" >/dev/null
git -C "$tmp_dir/install" config user.name "Home Library Test"
git -C "$tmp_dir/install" config user.email "test@example.invalid"

printf 'newer application code\n' > "$tmp_dir/source/application.txt"
git -C "$tmp_dir/source" add application.txt
git -C "$tmp_dir/source" commit -m newer >/dev/null
newer_sha="$(git -C "$tmp_dir/source" rev-parse HEAD)"
git -C "$tmp_dir/source" push origin main >/dev/null
git -C "$tmp_dir/source" tag v0.1.0
git -C "$tmp_dir/source" push origin v0.1.0 >/dev/null
git -C "$tmp_dir/install" pull --ff-only >/dev/null
git -C "$tmp_dir/install" fetch origin tag v0.1.0 >/dev/null

git -C "$tmp_dir/source" reset --hard "$baseline_sha" >/dev/null
printf 'rollback updater hotfix\n' > "$tmp_dir/source/updater.txt"
mkdir -p "$tmp_dir/source/scripts"
cp "$update_script" "$tmp_dir/source/scripts/update.sh"
git -C "$tmp_dir/source" add updater.txt scripts/update.sh
git -C "$tmp_dir/source" commit -m rollback-updater >/dev/null
rollback_sha="$(git -C "$tmp_dir/source" rev-parse HEAD)"
git -C "$tmp_dir/source" push --force origin main >/dev/null
git -C "$tmp_dir/source" tag -f v0.1.0 >/dev/null
git -C "$tmp_dir/source" push --force origin v0.1.0 >/dev/null

mkdir -p "$tmp_dir/bin" "$tmp_dir/install/logs"
cat > "$tmp_dir/bin/docker" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
printf 'VERSION=%s %s\n' "${VERSION:-}" "$*" >> "$DOCKER_LOG"
if [[ "${FAIL_BACKUP:-0}" == "1" && "$*" == *"sqlite3 /data/home_library.sqlite3"* ]]; then
  exit 1
fi
case "$*" in
  *"ps backend"*)
    if [[ "${BACKEND_RUNNING:-1}" == "1" ]]; then
      if [[ "${FORCE_UNHEALTHY:-0}" == "1" ]]; then
        printf 'backend running\n'
      else
        printf 'backend running healthy\n'
      fi
    fi
    ;;
  *"exec -T backend"*) printf '0.1.0\n' ;;
esac
SH
chmod +x "$tmp_dir/bin/docker"

cp -R "$tmp_dir/install" "$tmp_dir/backup-failure-install"
: > "$tmp_dir/backup-failure.log"
if HOME="$tmp_dir/home" \
  PATH="$tmp_dir/bin:/usr/bin:/bin" \
  DOCKER_LOG="$tmp_dir/backup-failure.log" \
  FAIL_BACKUP=1 \
  bash <(cat "$update_script") \
    --install-dir "$tmp_dir/backup-failure-install" \
    --version 0.1.0 >/dev/null 2>&1; then
  fail "update continued after the database backup command failed"
fi
[[ "$(git -C "$tmp_dir/backup-failure-install" rev-parse HEAD)" == "$newer_sha" ]] \
  || fail "checkout changed even though database backup failed"
if grep -Fq ' pull' "$tmp_dir/backup-failure.log"; then
  fail "image pull started even though database backup failed"
fi

cp -R "$tmp_dir/install" "$tmp_dir/stopped-backend-install"
: > "$tmp_dir/stopped-backend.log"
if HOME="$tmp_dir/home" \
  PATH="$tmp_dir/bin:/usr/bin:/bin" \
  DOCKER_LOG="$tmp_dir/stopped-backend.log" \
  BACKEND_RUNNING=0 \
  bash <(cat "$update_script") \
    --install-dir "$tmp_dir/stopped-backend-install" \
    --version 0.1.0 >/dev/null 2>&1; then
  fail "update continued without a running backend and verified backup"
fi
[[ "$(git -C "$tmp_dir/stopped-backend-install" rev-parse HEAD)" == "$newer_sha" ]] \
  || fail "checkout changed while the backend was stopped"

cp -R "$tmp_dir/install" "$tmp_dir/unhealthy-install"
: > "$tmp_dir/unhealthy.log"
if HOME="$tmp_dir/home" \
  PATH="$tmp_dir/bin:/usr/bin:/bin" \
  DOCKER_LOG="$tmp_dir/unhealthy.log" \
  FORCE_UNHEALTHY=1 \
  UPDATE_MAX_WAIT=0 \
  bash <(cat "$update_script") \
    --install-dir "$tmp_dir/unhealthy-install" \
    --version 0.1.0 >/dev/null 2>&1; then
  fail "update reported success after the new backend stayed unhealthy"
fi
grep -Fq "VERSION=0.1.0 compose -f $tmp_dir/unhealthy-install/docker-compose.prod.yml up -d --remove-orphans" \
  "$tmp_dir/unhealthy.log" \
  || fail "unhealthy-path test did not reach the service restart"

HOME="$tmp_dir/home" \
  PATH="$tmp_dir/bin:/usr/bin:/bin" \
  DOCKER_LOG="$tmp_dir/docker.log" \
  bash <(cat "$update_script") \
    --install-dir "$tmp_dir/install" \
    --version 0.1.0 >/dev/null

actual_sha="$(git -C "$tmp_dir/install" rev-parse HEAD)"
[[ "$actual_sha" == "$rollback_sha" ]] \
  || fail "installed checkout stayed at $actual_sha instead of syncing to rollback updater $rollback_sha"

grep -Fq '_sync_main_checkout()' "$tmp_dir/install/scripts/update.sh" \
  || fail "rollback replaced the safe updater with an older script"

git -C "$tmp_dir/install" for-each-ref \
  --format='%(objectname)' refs/heads/backup/home-library-update \
  | grep -Fqx "$newer_sha" \
  || fail "rewound server commit was not preserved on a backup branch"

grep -Fq "VERSION=0.1.0 compose -f $tmp_dir/install/docker-compose.prod.yml pull" \
  "$tmp_dir/docker.log" \
  || fail "target image was not pulled after synchronizing deployment files"

grep -Fq 'test -s /backups/pre_update_' "$tmp_dir/docker.log" \
  || fail "database backup was not verified inside the Docker backup volume"

echo "history rewind update tests passed"
