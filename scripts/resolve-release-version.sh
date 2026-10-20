#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 3 ]]; then
  echo "usage: $0 <ref-type> <ref-name> <run-number>" >&2
  exit 2
fi

ref_type="$1"
ref_name="$2"
run_number="$3"

if [[ "$ref_type" == "tag" ]]; then
  core='(0|[1-9][0-9]*)'
  prerelease_identifier='(0|[1-9][0-9]*|[0-9A-Za-z-]*[A-Za-z-][0-9A-Za-z-]*)'
  semver_regex="^v${core}\\.${core}\\.${core}(-${prerelease_identifier}(\\.${prerelease_identifier})*)?$"
  if [[ ! "$ref_name" =~ $semver_regex ]]; then
    echo "错误：Release tag 必须是 vMAJOR.MINOR.PATCH，可带合法 prerelease。" >&2
    exit 2
  fi
  version="${ref_name#v}"
elif [[ "$ref_type" == "branch" && "$ref_name" == "main" && "$run_number" =~ ^[1-9][0-9]*$ ]]; then
  version="0.1.${run_number}"
else
  echo "错误：只支持 main 分支或 SemVer Release tag。" >&2
  exit 2
fi

if (( ${#version} > 128 )); then
  echo "错误：发布版本不能超过 128 个字符。" >&2
  exit 2
fi

printf '%s\n' "$version"
