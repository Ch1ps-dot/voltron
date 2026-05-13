#!/usr/bin/env bash
set -euo pipefail

CONTAINER="${VOLTRON_CONTAINER:-}"
WORKDIR="${VOLTRON_DOCKER_WORKDIR:-/home/ubuntu/voltron}"

usage() {
  cat <<'EOF'
Usage:
  ./run_in_docker.sh -d <container> -s <target> -a <algo> -t <time> [extra cli.py args...]
  VOLTRON_CONTAINER=<container> ./run_in_docker.sh -s <target> -a <algo> -t <time>

Options:
  -d, --docker      Docker container name or ID. Can also be set with VOLTRON_CONTAINER.
  -s, --sut         Target name passed to cli.py.
  -a, --algorithm   Algorithm passed to cli.py.
  -t, --time        Time in minutes passed to cli.py.
  -h, --help        Show this help.

Environment:
  VOLTRON_CONTAINER       Default Docker container name or ID.
  VOLTRON_DOCKER_WORKDIR  Directory inside Docker. Default: /home/ubuntu/voltron

Example:
  ./run_in_docker.sh -d voltron-dev -s lightftp -a state -t 30
EOF
}

TARGET=""
ALGO=""
TIME=""
EXTRA_ARGS=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    -d|--docker|--container)
      CONTAINER="${2:-}"
      shift 2
      ;;
    -s|--sut|--target)
      TARGET="${2:-}"
      shift 2
      ;;
    -a|--algorithm|--algo)
      ALGO="${2:-}"
      shift 2
      ;;
    -t|--time)
      TIME="${2:-}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    --)
      shift
      EXTRA_ARGS+=("$@")
      break
      ;;
    *)
      EXTRA_ARGS+=("$1")
      shift
      ;;
  esac
done

if [[ -z "$CONTAINER" || -z "$TARGET" || -z "$ALGO" || -z "$TIME" ]]; then
  usage >&2
  exit 2
fi

if ! docker inspect "$CONTAINER" >/dev/null 2>&1; then
  echo "Docker container not found: $CONTAINER" >&2
  exit 1
fi

exec docker exec -it -w "$WORKDIR" "$CONTAINER" \
  uv run cli.py -s "$TARGET" -a "$ALGO" -t "$TIME" "${EXTRA_ARGS[@]}"
