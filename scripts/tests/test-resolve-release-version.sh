#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
script="${repo_root}/scripts/resolve-release-version.sh"

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

expect_version() {
  local ref_type="$1"
  local ref_name="$2"
  local run_number="$3"
  local expected="$4"
  local actual
  actual="$(bash "$script" "$ref_type" "$ref_name" "$run_number")"
  [[ "$actual" == "$expected" ]] || fail "$ref_name resolved to $actual, expected $expected"
}

expect_invalid() {
  local ref_name="$1"
  if bash "$script" tag "$ref_name" 42 >/dev/null 2>&1; then
    fail "$ref_name must be rejected"
  fi
}

expect_version tag v1.2.3 42 v1.2.3
expect_version tag v0.0.1-rc.1 42 v0.0.1-rc.1
expect_version tag v2.10.3-alpha.beta-7 42 v2.10.3-alpha.beta-7
expect_version branch main 42 0.1.42

expect_invalid v
expect_invalid vfoo
expect_invalid v1.2
expect_invalid v01.2.3
expect_invalid v1.02.3
expect_invalid v1.2.03
expect_invalid v1.2.3-01
expect_invalid v1.2.3+
expect_invalid v1.2.3+build

echo "release version tests passed"
