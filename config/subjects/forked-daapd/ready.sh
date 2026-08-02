#!/bin/bash

set -euo pipefail

host="${1:-${VOLTRON_READINESS_HOST:-127.0.0.1}}"
port="${2:-${VOLTRON_READINESS_PORT:-3689}}"
timeout="${3:-${VOLTRON_READINESS_TIMEOUT:-5}}"

python3 - "$host" "$port" "$timeout" <<'PY'
import socket
import sys

host = sys.argv[1]
port = int(sys.argv[2])
timeout = float(sys.argv[3])
request = (
    b"GET /server-info HTTP/1.1\r\n"
    + f"Host: {host}:{port}\r\n".encode("ascii")
    + b"User-Agent: Voltron-Readiness/1.0\r\n"
    + b"Connection: close\r\n\r\n"
)

try:
    with socket.create_connection((host, port), timeout=timeout) as sock:
        sock.settimeout(timeout)
        sock.sendall(request)
        response = sock.recv(4096)
except OSError as error:
    raise SystemExit(f"DAAP readiness failed: {error}") from None

if not response:
    raise SystemExit("DAAP readiness failed: empty response")
status_line = response.split(b"\r\n", 1)[0]
parts = status_line.split()
if len(parts) < 2 or not parts[0].startswith(b"HTTP/"):
    raise SystemExit(f"DAAP readiness failed: invalid status line {status_line!r}")
try:
    status = int(parts[1])
except ValueError as error:
    raise SystemExit(
        f"DAAP readiness failed: invalid status code {status_line!r}"
    ) from error
if not 200 <= status < 300:
    raise SystemExit(f"DAAP readiness failed: unexpected HTTP status {status}")
print(f"DAAP ready: {status_line.decode('latin-1', errors='replace')}")
PY
