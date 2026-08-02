#!/bin/bash

set -euo pipefail

config=/home/ubuntu/experiments/basic.conf
while read -r path; do
  [[ "$path" == /* ]] || continue
  rm -f -- "$path"
done < <(
  awk 'tolower($1) == "pidfile" || tolower($1) == "scoreboardfile" {print $2}' "$config"
)

exec /home/ubuntu/experiments/proftpd/proftpd \
  -n -c /home/ubuntu/experiments/basic.conf -X
