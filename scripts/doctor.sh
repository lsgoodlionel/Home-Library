#!/usr/bin/env bash
set -Eeuo pipefail

APP_NAME="Home Library"
REPO_HINT="Home-Library"
LOG_FILE="${PWD}/home-library-doctor-$(date +%Y%m%d-%H%M%S).log"

exec > >(tee -a "$LOG_FILE") 2>&1

section() {
  printf '\n========== %s ==========\n' "$1"
}

info() {
  printf '[INFO] %s\n' "$1"
}

warn() {
  printf '[WARN] %s\n' "$1"
}

fail() {
  printf '[ERROR] %s\n' "$1"
}

have() {
  command -v "$1" >/dev/null 2>&1
}

run() {
  printf '\n$ %s\n' "$*"
  "$@"
}

run_allow_fail() {
  printf '\n$ %s\n' "$*"
  "$@" || true
}

mask_env() {
  sed -E 's/(PASSWORD|PASS|SECRET|TOKEN|KEY|COOKIE)=.*/\1=*******/Ig'
}

as_root_hint() {
  if [ "$(id -u)" -ne 0 ]; then
    warn "当前不是 root。如果 Docker 或 systemctl 权限不足，请使用 sudo 重新执行。"
  fi
}

detect_compose_dir_from_containers() {
  if ! have docker; then
    return 1
  fi
  docker ps -a --format '{{.Names}}' 2>/dev/null \
    | grep -Ei 'home.*library|home-library|library.*backend|library.*frontend' \
    | while read -r container_name; do
        docker inspect "$container_name" \
          --format '{{ index .Config.Labels "com.docker.compose.project.working_dir" }}' 2>/dev/null || true
      done \
    | grep -v '^<no value>$' \
    | grep -v '^$' \
    | head -n 1
}

detect_compose_dir_from_files() {
  candidates=(
    "$PWD"
    "/opt/Home-Library"
    "/opt/home-library"
    "/srv/Home-Library"
    "/srv/home-library"
    "/var/www/Home-Library"
    "/var/www/home-library"
    "$HOME/Home-Library"
    "$HOME/home-library"
  )

  for dir in "${candidates[@]}"; do
    if [ -f "$dir/docker-compose.yml" ] || [ -f "$dir/compose.yml" ] || [ -f "$dir/docker-compose.yaml" ]; then
      printf '%s\n' "$dir"
      return 0
    fi
  done

  find /opt /srv /var/www "$HOME" -maxdepth 5 \
    \( -name docker-compose.yml -o -name compose.yml -o -name docker-compose.yaml \) \
    2>/dev/null \
    | grep -Ei "$REPO_HINT|home-library|library" \
    | head -n 1 \
    | xargs -r dirname
}

detect_compose_dir() {
  if [ "${1:-}" != "" ]; then
    printf '%s\n' "$1"
    return 0
  fi

  local from_container
  from_container="$(detect_compose_dir_from_containers || true)"
  if [ "$from_container" != "" ]; then
    printf '%s\n' "$from_container"
    return 0
  fi

  detect_compose_dir_from_files || true
}

compose_cmd() {
  if docker compose version >/dev/null 2>&1; then
    docker compose "$@"
  elif have docker-compose; then
    docker-compose "$@"
  else
    fail "未找到 docker compose 或 docker-compose"
    return 127
  fi
}

check_docker() {
  section "Docker 状态"
  if ! have docker; then
    fail "未安装 Docker。请先安装 Docker Engine 和 Docker Compose。"
    exit 2
  fi

  run_allow_fail docker --version
  run_allow_fail docker compose version

  if ! docker info >/dev/null 2>&1; then
    warn "Docker daemon 未响应，尝试启动 docker 服务。"
    if have systemctl; then
      run_allow_fail sudo systemctl start docker
      run_allow_fail sudo systemctl enable docker
    fi
  fi

  if ! docker info >/dev/null 2>&1; then
    fail "Docker daemon 仍不可用。请检查 systemctl status docker。"
    exit 3
  fi
}

print_system_info() {
  section "服务器信息"
  run_allow_fail uname -a
  run_allow_fail date
  run_allow_fail df -h
  run_allow_fail free -h
}

print_project_info() {
  local dir="$1"
  section "部署目录"
  info "检测到部署目录：$dir"
  cd "$dir"
  run_allow_fail pwd
  run_allow_fail ls -la

  if [ -d .git ]; then
    section "Git 信息"
    run_allow_fail git remote -v
    run_allow_fail git branch --show-current
    run_allow_fail git rev-parse --short HEAD
    run_allow_fail git status --short
  else
    warn "该目录不是 Git 仓库，无法检查代码版本。"
  fi

  section "环境配置摘要"
  if [ -f .env ]; then
    mask_env < .env
  else
    warn "未发现 .env 文件。"
  fi
}

print_compose_info() {
  section "Docker Compose 配置"
  run_allow_fail compose_cmd config --services
  run_allow_fail compose_cmd ps
  section "相关容器"
  run_allow_fail docker ps -a --filter "name=home" --filter "name=library"
}

try_health_urls() {
  section "HTTP 健康检查"
  local urls=(
    "http://127.0.0.1/api/health"
    "http://127.0.0.1:80/api/health"
    "http://127.0.0.1:8080/api/health"
    "http://127.0.0.1:8000/api/health"
  )

  local ok=1
  for url in "${urls[@]}"; do
    printf '\n$ curl -fsS --max-time 5 %s\n' "$url"
    if curl -fsS --max-time 5 "$url"; then
      printf '\n'
      ok=0
      break
    else
      printf '不可用：%s\n' "$url"
    fi
  done
  return "$ok"
}

show_logs() {
  section "最近日志"
  run_allow_fail compose_cmd logs --tail=120 backend
  run_allow_fail compose_cmd logs --tail=80 frontend
}

repair_compose() {
  section "修复运行状态"
  info "先尝试非破坏性启动已有服务。"
  run compose_cmd up -d --remove-orphans

  sleep 8
  run_allow_fail compose_cmd ps

  if try_health_urls; then
    info "服务已恢复。"
    return 0
  fi

  warn "健康检查仍失败，尝试重新构建并启动。"
  run compose_cmd up -d --build --remove-orphans

  sleep 12
  run_allow_fail compose_cmd ps

  if try_health_urls; then
    info "重建后服务已恢复。"
    return 0
  fi

  fail "自动修复后仍未恢复，请查看下方日志。"
  show_logs
  return 1
}

main() {
  section "$APP_NAME 一键诊断与修复"
  info "日志文件：$LOG_FILE"
  as_root_hint
  print_system_info
  check_docker

  local compose_dir
  compose_dir="$(detect_compose_dir "${1:-}")"
  if [ "$compose_dir" = "" ] || [ ! -d "$compose_dir" ]; then
    fail "未能自动定位部署目录。请传入项目目录，例如：bash scripts/doctor.sh /opt/Home-Library"
    section "当前 Docker 容器"
    run_allow_fail docker ps -a
    exit 4
  fi

  print_project_info "$compose_dir"
  print_compose_info
  show_logs
  repair_compose

  section "完成"
  info "诊断修复结束。完整日志已保存到：$LOG_FILE"
}

main "$@"
