"""Small dependency-free HTTP API and dashboard for Voltron."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
from functools import partial
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import threading
from typing import Any
from urllib.parse import parse_qs, urlparse
import uuid

from voltron.config_loader import load_runtime_config
from voltron.configs import configs


RUN_ID_PATTERN = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,95}$')
CSV_FILES = {
    'phases': 'phase_metrics.csv',
    'llm_usage': 'llm_usage_metrics.csv',
    'learning': 'model_learning_iterations.csv',
    'generator': 'generator_iteration_metrics.csv',
    'iterations': 'iteration_state_metrics.csv',
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def target_catalog(base_path: Path) -> list[dict[str, Any]]:
    raw = load_runtime_config(base_path / 'config')
    targets = []
    for name, value in raw.items():
        if not isinstance(value, dict) or not {
            'protocol', 'host', 'port', 'trans_layer'
        }.issubset(value):
            continue
        targets.append({
            'name': name,
            'protocol': str(value['protocol']),
            'host': str(value['host']),
            'port': int(value['port']),
            'transport': str(value['trans_layer']).upper(),
            'deployment': str(value.get('sut_deployment', 'local')),
            'rfc_count': len(value.get('rfc_name', [])),
        })
    return sorted(targets, key=lambda item: item['name'])


def parse_key_value_status(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    values: dict[str, Any] = {}
    try:
        for line in path.read_text(encoding='utf-8', errors='replace').splitlines():
            if ':' not in line:
                continue
            key, value = line.split(':', 1)
            values[key.strip()] = coerce_scalar(value.strip())
    except OSError:
        return {}
    return values


def coerce_scalar(value: str) -> Any:
    lowered = value.lower()
    if lowered == 'true':
        return True
    if lowered == 'false':
        return False
    if value == '':
        return ''
    try:
        if any(marker in value for marker in ('.', 'e', 'E')):
            return float(value)
        return int(value)
    except ValueError:
        return value


def read_csv(path: Path, limit: int = 500) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    try:
        with path.open(encoding='utf-8', errors='replace', newline='') as stream:
            rows = list(csv.DictReader(stream))[-limit:]
    except (OSError, csv.Error):
        return []
    return [
        {key: coerce_scalar(value) for key, value in row.items()}
        for row in rows
    ]


def tail_text(path: Path, lines: int = 180, max_bytes: int = 256_000) -> str:
    if not path.is_file():
        return ''
    try:
        with path.open('rb') as stream:
            stream.seek(0, os.SEEK_END)
            size = stream.tell()
            stream.seek(max(0, size - max_bytes))
            raw = stream.read()
    except OSError:
        return ''
    decoded = raw.decode('utf-8', errors='replace').splitlines()
    return '\n'.join(decoded[-lines:])


class RunManager:
    """Own web-launched fuzzer processes and adapt result files for the UI."""

    def __init__(self, base_path: Path) -> None:
        self.base_path = Path(base_path).resolve()
        self.runs_root = self.base_path / 'web-runs'
        self.runs_root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._processes: dict[str, subprocess.Popen] = {}
        self._streams: dict[str, Any] = {}

    def _run_path(self, run_id: str) -> Path:
        if not RUN_ID_PATTERN.fullmatch(run_id):
            raise KeyError(run_id)
        path = (self.runs_root / run_id).resolve()
        if path.parent != self.runs_root.resolve():
            raise KeyError(run_id)
        return path

    def _metadata_path(self, run_id: str) -> Path:
        return self._run_path(run_id) / 'web_run.json'

    def _read_metadata(self, run_id: str) -> dict[str, Any]:
        path = self._metadata_path(run_id)
        if not path.is_file():
            raise KeyError(run_id)
        try:
            payload = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError) as error:
            raise KeyError(run_id) from error
        return payload if isinstance(payload, dict) else {}

    def _write_metadata(self, run_id: str, payload: dict[str, Any]) -> None:
        path = self._metadata_path(run_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix('.json.tmp')
        temporary.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + '\n',
            encoding='utf-8',
        )
        temporary.replace(path)

    def _live_process(self, run_id: str) -> subprocess.Popen | None:
        process = self._processes.get(run_id)
        return process if process is not None and process.poll() is None else None

    def _recorded_process_alive(self, run_id: str) -> bool:
        """Recognize a surviving run after the web server itself restarted."""
        process = self._live_process(run_id)
        if process is not None:
            return True
        try:
            metadata = self._read_metadata(run_id)
            pid = int(metadata.get('pid', 0))
            command_line = Path(f'/proc/{pid}/cmdline').read_bytes().split(b'\0')
        except (KeyError, OSError, TypeError, ValueError):
            return False
        tokens = [token.decode('utf-8', errors='replace') for token in command_line]
        expected_output = f'web-runs/{run_id}'
        return (
            str(self.base_path / 'cli.py') in tokens
            and expected_output in tokens
        )

    def start(self, options: dict[str, Any]) -> dict[str, Any]:
        targets = {item['name'] for item in target_catalog(self.base_path)}
        target = str(options.get('target', '')).strip()
        if target not in targets:
            raise ValueError('请选择有效的测试目标')
        try:
            duration = int(options.get('duration_minutes', 30))
        except (TypeError, ValueError) as error:
            raise ValueError('运行时长必须是整数分钟') from error
        if not 1 <= duration <= 1440:
            raise ValueError('运行时长须在 1 到 1440 分钟之间')

        with self._lock:
            if any(
                self._recorded_process_alive(path.name)
                for path in self.runs_root.iterdir()
                if path.is_dir() and RUN_ID_PATTERN.fullmatch(path.name)
            ):
                raise RuntimeError('已有模糊测试任务正在运行，请先停止或等待完成')

            run_id = (
                f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-"
                f"{re.sub(r'[^a-zA-Z0-9_.-]+', '-', target)[:40]}-"
                f"{uuid.uuid4().hex[:6]}"
            )
            output = f'web-runs/{run_id}'
            run_path = self._run_path(run_id)
            run_path.mkdir(parents=True)
            flags = {
                'spec_knowledge': bool(options.get('spec_knowledge', True)),
                'state_learning': bool(options.get('state_learning', True)),
                'guided_scheduling': bool(options.get('guided_scheduling', True)),
                'observer': bool(options.get('observer', True)),
                'compliance_analysis': bool(options.get('compliance_analysis', False)),
                'load_aflnet_seeds': bool(options.get('load_aflnet_seeds', True)),
                'offline_mutator_only': bool(options.get('offline_mutator_only', False)),
            }
            command = [
                sys.executable, str(self.base_path / 'cli.py'),
                '--sut', target,
                '--algorithm', 'state',
                '--time', str(duration),
                '--output', output,
                '--spec-knowledge' if flags['spec_knowledge'] else '--no-spec-knowledge',
                '--state-learning' if flags['state_learning'] else '--no-state-learning',
                '--guided-scheduling' if flags['guided_scheduling'] else '--no-guided-scheduling',
                '--observer' if flags['observer'] else '--no-observer',
                '--compliance-analysis' if flags['compliance_analysis'] else '--no-compliance-analysis',
                '--load-aflnet-seeds' if flags['load_aflnet_seeds'] else '--no-load-aflnet-seeds',
            ]
            if flags['offline_mutator_only']:
                command.append('--offline-mutator-only')

            metadata = {
                'id': run_id,
                'target': target,
                'algorithm': 'state',
                'duration_minutes': duration,
                'created_at': utc_now(),
                'started_at': utc_now(),
                'finished_at': None,
                'status': 'starting',
                'exit_code': None,
                'options': flags,
            }
            self._write_metadata(run_id, metadata)
            console_path = run_path / 'web-console.log'
            stream = console_path.open('ab', buffering=0)
            try:
                process = subprocess.Popen(
                    command,
                    cwd=self.base_path,
                    stdin=subprocess.DEVNULL,
                    stdout=stream,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
            except BaseException:
                stream.close()
                metadata.update(status='failed_to_start', finished_at=utc_now())
                self._write_metadata(run_id, metadata)
                raise
            metadata.update(status='running', pid=process.pid)
            self._write_metadata(run_id, metadata)
            self._processes[run_id] = process
            self._streams[run_id] = stream
            threading.Thread(
                target=self._watch,
                args=(run_id, process),
                name=f'voltron-web-{run_id}',
                daemon=True,
            ).start()
        return self.detail(run_id)

    def _watch(self, run_id: str, process: subprocess.Popen) -> None:
        exit_code = process.wait()
        with self._lock:
            try:
                metadata = self._read_metadata(run_id)
                metadata.update(
                    exit_code=exit_code,
                    finished_at=utc_now(),
                    status='completed' if exit_code == 0 else 'stopped' if exit_code == 130 else 'failed',
                )
                self._write_metadata(run_id, metadata)
            finally:
                stream = self._streams.pop(run_id, None)
                if stream is not None:
                    stream.close()

    def stop(self, run_id: str) -> dict[str, Any]:
        with self._lock:
            metadata = self._read_metadata(run_id)
            process = self._live_process(run_id)
            if process is None and not self._recorded_process_alive(run_id):
                raise RuntimeError('该任务当前不在本 Web 服务的运行队列中')
            try:
                os.killpg(
                    process.pid if process is not None else int(metadata['pid']),
                    signal.SIGINT,
                )
            except ProcessLookupError:
                pass
            metadata['status'] = 'stopping'
            metadata['stop_requested_at'] = utc_now()
            self._write_metadata(run_id, metadata)
        return self.detail(run_id)

    def list_runs(self) -> list[dict[str, Any]]:
        runs = []
        for path in self.runs_root.iterdir():
            if not path.is_dir() or not RUN_ID_PATTERN.fullmatch(path.name):
                continue
            try:
                detail = self.detail(path.name, include_metrics=False)
            except KeyError:
                continue
            runs.append(detail)
        return sorted(runs, key=lambda item: item.get('created_at', ''), reverse=True)

    def detail(self, run_id: str, include_metrics: bool = True) -> dict[str, Any]:
        run_path = self._run_path(run_id)
        metadata = self._read_metadata(run_id)
        status = parse_key_value_status(
            run_path / 'diagnostics' / 'status' / 'fuzzer_status'
        )
        final_path = run_path / 'diagnostics' / 'status' / 'run_status.json'
        final_status: dict[str, Any] = {}
        if final_path.is_file():
            try:
                final_status = json.loads(final_path.read_text(encoding='utf-8'))
            except (OSError, json.JSONDecodeError):
                pass

        process = self._live_process(run_id)
        is_active = process is not None or self._recorded_process_alive(run_id)
        effective_status = str(
            final_status.get('run_status')
            or ('running' if is_active else metadata.get('status', 'unknown'))
        )
        result = {
            **metadata,
            'status': effective_status,
            'active': is_active,
            'runtime': status,
            'final': final_status,
        }
        if include_metrics:
            result['metrics'] = {
                key: read_csv(run_path / filename)
                for key, filename in CSV_FILES.items()
            }
            states = read_csv(run_path / 'states.csv', limit=1000)
            result['state_summary'] = summarize_states(states)
        return result

    def logs(self, run_id: str, lines: int) -> dict[str, str]:
        run_path = self._run_path(run_id)
        self._read_metadata(run_id)
        lines = max(20, min(lines, 1000))
        return {
            'console': tail_text(run_path / 'web-console.log', lines),
            'fuzzer': tail_text(run_path / 'diagnostics' / 'logs' / 'fuzz.log', lines),
            'llm': tail_text(run_path / 'diagnostics' / 'logs' / 'llm.log', lines),
        }


def summarize_states(rows: list[dict[str, Any]]) -> dict[str, Any]:
    nodes = 0
    edges = 0
    discoveries: list[dict[str, Any]] = []
    for row in rows:
        kind = str(row.get('data_type', ''))
        try:
            value = max(0, int(float(row.get('data', 0) or 0)))
        except (TypeError, ValueError):
            continue
        if kind == 'nodes':
            nodes = value
        elif kind == 'edges':
            edges = value
            raw_time = row.get('elapsed_seconds', row.get('time', ''))
            discoveries.append({
                'time': coerce_scalar(str(raw_time)),
                'nodes': nodes,
                'edges': edges,
            })
    return {
        'nodes': nodes,
        'edges': edges,
        'discoveries': discoveries[-120:],
    }


class ApiHandler(SimpleHTTPRequestHandler):
    server_version = 'VoltronWeb/0.1'

    def __init__(self, *args, manager: RunManager, static_dir: Path, **kwargs):
        self.manager = manager
        super().__init__(*args, directory=str(static_dir), **kwargs)

    def end_headers(self) -> None:
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header(
            'Content-Security-Policy',
            "default-src 'self'; script-src 'self'; style-src 'self' "
            "'unsafe-inline'; img-src 'self' data:; connect-src 'self'; "
            "object-src 'none'; frame-ancestors 'none'",
        )
        super().end_headers()

    def _json(self, payload: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
        encoded = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(encoded)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(encoded)

    def _error(self, status: HTTPStatus, message: str) -> None:
        self._json({'error': message}, status)

    def _body(self) -> dict[str, Any]:
        content_type = self.headers.get('Content-Type', '').split(';', 1)[0]
        if content_type.strip().lower() != 'application/json':
            raise ValueError('请求内容类型必须是 application/json')
        try:
            length = int(self.headers.get('Content-Length', '0'))
        except ValueError as error:
            raise ValueError('无效的请求长度') from error
        if length > 64 * 1024:
            raise ValueError('请求内容过大')
        try:
            payload = json.loads(self.rfile.read(length) or b'{}')
        except json.JSONDecodeError as error:
            raise ValueError('请求内容不是有效 JSON') from error
        if not isinstance(payload, dict):
            raise ValueError('请求内容必须是 JSON 对象')
        return payload

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        parts = [part for part in parsed.path.split('/') if part]
        try:
            if parsed.path == '/api/targets':
                self._json({'targets': target_catalog(self.manager.base_path)})
                return
            if parsed.path == '/api/runs':
                self._json({'runs': self.manager.list_runs()})
                return
            if len(parts) == 3 and parts[:2] == ['api', 'runs']:
                self._json(self.manager.detail(parts[2]))
                return
            if len(parts) == 4 and parts[:2] == ['api', 'runs'] and parts[3] == 'logs':
                query = parse_qs(parsed.query)
                try:
                    lines = int(query.get('lines', ['180'])[0])
                except ValueError:
                    lines = 180
                self._json(self.manager.logs(parts[2], lines))
                return
        except KeyError:
            self._error(HTTPStatus.NOT_FOUND, '任务不存在')
            return
        except Exception as error:
            self._error(HTTPStatus.INTERNAL_SERVER_ERROR, str(error))
            return
        if parsed.path.startswith('/api/'):
            self._error(HTTPStatus.NOT_FOUND, '接口不存在')
            return
        if parsed.path in {'/', '/index.html'}:
            self.path = '/index.html'
        super().do_GET()

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        parts = [part for part in parsed.path.split('/') if part]
        try:
            if parsed.path == '/api/runs':
                self._json(self.manager.start(self._body()), HTTPStatus.CREATED)
                return
            if len(parts) == 4 and parts[:2] == ['api', 'runs'] and parts[3] == 'stop':
                self._json(self.manager.stop(parts[2]))
                return
            self._error(HTTPStatus.NOT_FOUND, '接口不存在')
        except KeyError:
            self._error(HTTPStatus.NOT_FOUND, '任务不存在')
        except (ValueError, RuntimeError) as error:
            self._error(HTTPStatus.CONFLICT, str(error))
        except Exception as error:
            self._error(HTTPStatus.INTERNAL_SERVER_ERROR, str(error))

    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stderr.write(f'[web] {self.address_string()} - {fmt % args}\n')


def create_server(host: str, port: int, base_path: Path | None = None) -> ThreadingHTTPServer:
    base = Path(base_path or configs.base_path).resolve()
    static_dir = Path(__file__).with_name('static')
    manager = RunManager(base)
    handler = partial(ApiHandler, manager=manager, static_dir=static_dir)
    server = ThreadingHTTPServer((host, port), handler)
    server.daemon_threads = True
    return server


def main() -> None:
    parser = argparse.ArgumentParser(description='Voltron Web 控制台')
    parser.add_argument('--host', default='127.0.0.1', help='监听地址')
    parser.add_argument('--port', default=8088, type=int, help='监听端口')
    args = parser.parse_args()
    server = create_server(args.host, args.port)
    print(f'Voltron Web: http://{args.host}:{server.server_port}')
    if args.host not in {'127.0.0.1', 'localhost', '::1'}:
        print('WARNING: Web 控制台没有身份认证，请勿直接暴露到不可信网络。')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
