#!/usr/bin/env bash

set -euo pipefail

usage() {
	cat <<'EOF'
Usage: ./rfc_download.sh <rfc-id> [<rfc-id> ...]

Examples:
  ./rfc_download.sh rfc9041
  ./rfc_download.sh 9041 rfc959 RFC9110
EOF
}

if [[ $# -lt 1 ]]; then
	usage
	exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
RFC_DIR="${PROJECT_DIR}/config/rfcs"
mkdir -p "${RFC_DIR}"

download_file() {
	local url="$1"
	local out_file="$2"

	if command -v curl >/dev/null 2>&1; then
		curl -fsSL "${url}" -o "${out_file}"
		return
	fi

	if command -v wget >/dev/null 2>&1; then
		wget -q "${url}" -O "${out_file}"
		return
	fi

	echo "Error: neither curl nor wget is installed." >&2
	exit 1
}

for raw in "$@"; do
	input="$(echo "${raw}" | tr '[:upper:]' '[:lower:]')"

	if [[ "${input}" =~ ^rfc([0-9]+)$ ]]; then
		rfc_num="${BASH_REMATCH[1]}"
	elif [[ "${input}" =~ ^([0-9]+)$ ]]; then
		rfc_num="${BASH_REMATCH[1]}"
	else
		echo "Skip: invalid RFC id '${raw}'. Use formats like rfc9041 or 9041." >&2
		continue
	fi

	file_name="rfc${rfc_num}.txt"
	url="https://www.rfc-editor.org/rfc/${file_name}"
	target="${RFC_DIR}/${file_name}"

	if [[ -f "${target}" ]]; then
		echo "Skip: already exists -> ${target}"
		continue
	fi

	tmp_file="${target}.tmp"
	echo "Downloading ${url} ..."

	if download_file "${url}" "${tmp_file}"; then
		mv "${tmp_file}" "${target}"
		echo "Saved -> ${target}"
	else
		rm -f "${tmp_file}"
		echo "Failed: ${url}" >&2
	fi
done
