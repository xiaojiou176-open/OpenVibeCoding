#!/usr/bin/env bash
set -euo pipefail

if [[ -n "${__OPENVIBECODING_RELEASE_TOOL_HELPERS_LOADED:-}" ]]; then
  return 0
fi
readonly __OPENVIBECODING_RELEASE_TOOL_HELPERS_LOADED=1

__openvibecoding_release_tool_root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
source "${__openvibecoding_release_tool_root_dir}/scripts/lib/toolchain_env.sh"

openvibecoding_release_tool_os() {
  case "$(uname -s)" in
    Darwin)
      printf '%s\n' "darwin"
      ;;
    Linux)
      printf '%s\n' "linux"
      ;;
    *)
      echo "❌ unsupported operating system for release tool bootstrap: $(uname -s)" >&2
      return 1
      ;;
  esac
}

openvibecoding_release_tool_arch() {
  case "$(uname -m)" in
    arm64|aarch64)
      printf '%s\n' "arm64"
      ;;
    x86_64|amd64)
      printf '%s\n' "amd64"
      ;;
    *)
      echo "❌ unsupported architecture for release tool bootstrap: $(uname -m)" >&2
      return 1
      ;;
  esac
}

openvibecoding_release_tool_bin_dir() {
  local root_dir="${1:?root_dir required}"
  local tool_name="${2:?tool_name required}"
  local version="${3:?version required}"
  local toolchain_root
  toolchain_root="$(openvibecoding_toolchain_cache_root "$root_dir")"
  printf '%s\n' "${toolchain_root}/release-tools/${tool_name}/${version}"
}

openvibecoding_release_tool_cache_dir() {
  local root_dir="${1:?root_dir required}"
  local tool_name="${2:?tool_name required}"
  local toolchain_root
  toolchain_root="$(openvibecoding_toolchain_cache_root "$root_dir")"
  printf '%s\n' "${toolchain_root}/release-tools/${tool_name}/cache"
}

_openvibecoding_release_tool_tmp_dir() {
  local root_dir="${1:?root_dir required}"
  local tool_name="${2:?tool_name required}"
  local tmp_root
  tmp_root="$(openvibecoding_machine_tmp_root "$root_dir")"
  mkdir -p "$tmp_root"
  mktemp -d "${tmp_root}/${tool_name}.XXXXXX"
}

_openvibecoding_install_release_binary() {
  local root_dir="${1:?root_dir required}"
  local tool_name="${2:?tool_name required}"
  local version="${3:?version required}"
  local archive_url="${4:?archive_url required}"
  local archive_name="${5:?archive_name required}"
  local binary_name="${6:?binary_name required}"

  local bin_dir
  bin_dir="$(openvibecoding_release_tool_bin_dir "$root_dir" "$tool_name" "$version")"
  local target_bin="${bin_dir}/${binary_name}"
  if [[ -x "$target_bin" ]]; then
    printf '%s\n' "$target_bin"
    return 0
  fi

  local tmp_dir
  tmp_dir="$(_openvibecoding_release_tool_tmp_dir "$root_dir" "$tool_name")"
  mkdir -p "$bin_dir"

  curl -fsSL "$archive_url" -o "${tmp_dir}/${archive_name}"
  case "$archive_name" in
    *.tar.gz|*.tgz)
      tar -xzf "${tmp_dir}/${archive_name}" -C "$tmp_dir"
      ;;
    *.zip)
      unzip -q "${tmp_dir}/${archive_name}" -d "$tmp_dir"
      ;;
    *)
      echo "❌ unsupported archive format for ${tool_name}: ${archive_name}" >&2
      rm -rf "$tmp_dir"
      return 1
      ;;
  esac

  local extracted_bin
  extracted_bin="$(find "$tmp_dir" -type f -name "$binary_name" | head -n 1 || true)"
  if [[ -z "$extracted_bin" ]]; then
    echo "❌ failed to find ${binary_name} inside ${archive_name}" >&2
    rm -rf "$tmp_dir"
    return 1
  fi

  install -m 0755 "$extracted_bin" "$target_bin"
  rm -rf "$tmp_dir"
  printf '%s\n' "$target_bin"
}

openvibecoding_actionlint_version() {
  printf '%s\n' "${OPENVIBECODING_ACTIONLINT_VERSION:-1.7.12}"
}

openvibecoding_actionlint_bin() {
  local root_dir="${1:?root_dir required}"
  local version
  version="$(openvibecoding_actionlint_version)"
  local os arch asset
  os="$(openvibecoding_release_tool_os)"
  arch="$(openvibecoding_release_tool_arch)"
  case "${os}/${arch}" in
    darwin/amd64) asset="actionlint_${version}_darwin_amd64.tar.gz" ;;
    darwin/arm64) asset="actionlint_${version}_darwin_arm64.tar.gz" ;;
    linux/amd64) asset="actionlint_${version}_linux_amd64.tar.gz" ;;
    linux/arm64) asset="actionlint_${version}_linux_arm64.tar.gz" ;;
    *)
      echo "❌ unsupported actionlint platform ${os}/${arch}" >&2
      return 1
      ;;
  esac
  _openvibecoding_install_release_binary \
    "$root_dir" \
    "actionlint" \
    "$version" \
    "https://github.com/rhysd/actionlint/releases/download/v${version}/${asset}" \
    "$asset" \
    "actionlint"
}

openvibecoding_zizmor_version() {
  printf '%s\n' "${OPENVIBECODING_ZIZMOR_VERSION:-1.23.1}"
}

openvibecoding_zizmor_bin() {
  local root_dir="${1:?root_dir required}"
  local version
  version="$(openvibecoding_zizmor_version)"
  local os arch asset
  os="$(openvibecoding_release_tool_os)"
  arch="$(openvibecoding_release_tool_arch)"
  case "${os}/${arch}" in
    darwin/amd64) asset="zizmor-x86_64-apple-darwin.tar.gz" ;;
    darwin/arm64) asset="zizmor-aarch64-apple-darwin.tar.gz" ;;
    linux/amd64) asset="zizmor-x86_64-unknown-linux-gnu.tar.gz" ;;
    linux/arm64) asset="zizmor-aarch64-unknown-linux-gnu.tar.gz" ;;
    *)
      echo "❌ unsupported zizmor platform ${os}/${arch}" >&2
      return 1
      ;;
  esac
  _openvibecoding_install_release_binary \
    "$root_dir" \
    "zizmor" \
    "$version" \
    "https://github.com/zizmorcore/zizmor/releases/download/v${version}/${asset}" \
    "$asset" \
    "zizmor"
}

openvibecoding_trivy_version() {
  printf '%s\n' "${OPENVIBECODING_TRIVY_VERSION:-0.69.3}"
}

openvibecoding_trivy_bin() {
  local root_dir="${1:?root_dir required}"
  local version
  version="$(openvibecoding_trivy_version)"
  local os arch asset
  os="$(openvibecoding_release_tool_os)"
  arch="$(openvibecoding_release_tool_arch)"
  case "${os}/${arch}" in
    darwin/amd64) asset="trivy_${version}_macOS-64bit.tar.gz" ;;
    darwin/arm64) asset="trivy_${version}_macOS-ARM64.tar.gz" ;;
    linux/amd64) asset="trivy_${version}_Linux-64bit.tar.gz" ;;
    linux/arm64) asset="trivy_${version}_Linux-ARM64.tar.gz" ;;
    *)
      echo "❌ unsupported trivy platform ${os}/${arch}" >&2
      return 1
      ;;
  esac
  _openvibecoding_install_release_binary \
    "$root_dir" \
    "trivy" \
    "$version" \
    "https://github.com/aquasecurity/trivy/releases/download/v${version}/${asset}" \
    "$asset" \
    "trivy"
}

openvibecoding_gitleaks_version() {
  printf '%s\n' "${OPENVIBECODING_GITLEAKS_VERSION:-8.30.1}"
}

openvibecoding_gitleaks_bin() {
  local root_dir="${1:?root_dir required}"
  local version
  version="$(openvibecoding_gitleaks_version)"
  local os arch asset
  os="$(openvibecoding_release_tool_os)"
  arch="$(openvibecoding_release_tool_arch)"
  case "${os}/${arch}" in
    darwin/amd64) asset="gitleaks_${version}_darwin_x64.tar.gz" ;;
    darwin/arm64) asset="gitleaks_${version}_darwin_arm64.tar.gz" ;;
    linux/amd64) asset="gitleaks_${version}_linux_x64.tar.gz" ;;
    linux/arm64) asset="gitleaks_${version}_linux_arm64.tar.gz" ;;
    *)
      echo "❌ unsupported gitleaks platform ${os}/${arch}" >&2
      return 1
      ;;
  esac
  _openvibecoding_install_release_binary \
    "$root_dir" \
    "gitleaks" \
    "$version" \
    "https://github.com/gitleaks/gitleaks/releases/download/v${version}/${asset}" \
    "$asset" \
    "gitleaks"
}

openvibecoding_trufflehog_version() {
  printf '%s\n' "${OPENVIBECODING_TRUFFLEHOG_VERSION:-3.94.2}"
}

openvibecoding_trufflehog_bin() {
  local root_dir="${1:?root_dir required}"
  local version
  version="$(openvibecoding_trufflehog_version)"
  local os arch asset
  os="$(openvibecoding_release_tool_os)"
  arch="$(openvibecoding_release_tool_arch)"
  case "${os}/${arch}" in
    darwin/amd64) asset="trufflehog_${version}_darwin_amd64.tar.gz" ;;
    darwin/arm64) asset="trufflehog_${version}_darwin_arm64.tar.gz" ;;
    linux/amd64) asset="trufflehog_${version}_linux_amd64.tar.gz" ;;
    linux/arm64) asset="trufflehog_${version}_linux_arm64.tar.gz" ;;
    *)
      echo "❌ unsupported trufflehog platform ${os}/${arch}" >&2
      return 1
      ;;
  esac
  _openvibecoding_install_release_binary \
    "$root_dir" \
    "trufflehog" \
    "$version" \
    "https://github.com/trufflesecurity/trufflehog/releases/download/v${version}/${asset}" \
    "$asset" \
    "trufflehog"
}
