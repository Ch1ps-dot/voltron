#!/bin/bash

set -euo pipefail

config=/home/ubuntu/experiments/basic.conf
if [[ ! -r "$config" ]]; then
  echo "ProFTPD setup failed: missing $config" >&2
  exit 1
fi

while read -r path; do
  [[ "$path" == /* ]] || continue
  mkdir -p "$(dirname "$path")"
done < <(
  awk 'tolower($1) == "pidfile" || tolower($1) == "scoreboardfile" {print $2}' "$config"
)

echo "ProFTPD environment ready"
