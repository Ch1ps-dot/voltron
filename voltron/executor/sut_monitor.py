from dataclasses import dataclass
import json
import socket
from typing import Any
from urllib import error, parse, request

from voltron.utils.logger import logger_fuzz as logger


RUNNING = 'RUNNING'
EXITED = 'EXITED'
CRASHED = 'CRASHED'
UNREACHABLE = 'UNREACHABLE'
UNKNOWN = 'UNKNOWN'


@dataclass
class SUTStatus:
    state: str = UNKNOWN
    returncode: int | None = None
    stdout: str = ''
    stderr: str = ''
    logs: str = ''
    process_running: bool | None = None
    port_listening: bool | None = None
    detail: str = ''


class RemoteSUTProcess:
    """Small process-like crash evidence container for remote SUTs."""

    def __init__(
        self,
        status: SUTStatus
    ) -> None:
        self.pid = 'remote'
        self.returncode = status.returncode

    def poll(
        self
    ) -> int | None:
        return self.returncode


class SUTMonitor:
    def start(
        self
    ) -> None:
        return None

    def is_ready(
        self
    ) -> bool:
        return False

    def status(
        self
    ) -> SUTStatus:
        return SUTStatus()

    def collect_failure_evidence(
        self
    ) -> SUTStatus:
        return self.status()

    def stop(
        self
    ) -> None:
        return None


class NoopSUTMonitor(SUTMonitor):
    def __init__(
        self,
        host: str,
        port: int,
        trans_layer: str,
        timeout_s: float = 1.0
    ) -> None:
        self.host = host
        self.port = port
        self.trans_layer = trans_layer
        self.timeout_s = timeout_s

    def is_ready(
        self
    ) -> bool:
        if self.trans_layer != 'tcp':
            return True
        try:
            with socket.create_connection(
                (self.host, self.port),
                timeout=self.timeout_s,
            ):
                return True
        except OSError:
            return False

    def status(
        self
    ) -> SUTStatus:
        ready = self.is_ready()
        return SUTStatus(
            state=RUNNING if ready else UNKNOWN,
            port_listening=ready,
        )


class AgentSUTMonitor(SUTMonitor):
    def __init__(
        self,
        url: str,
        host: str,
        port: int,
        trans_layer: str,
        timeout_s: float = 1.0,
        log_tail: int = 200
    ) -> None:
        self.url = url.rstrip('/')
        self.host = host
        self.port = port
        self.trans_layer = trans_layer
        self.timeout_s = timeout_s
        self.log_tail = log_tail

    def start(
        self
    ) -> None:
        self._post_optional('/start')

    def stop(
        self
    ) -> None:
        self._post_optional('/stop')

    def is_ready(
        self
    ) -> bool:
        status = self.status()
        if status.port_listening is not None:
            return status.port_listening
        return NoopSUTMonitor(
            self.host,
            self.port,
            self.trans_layer,
            self.timeout_s,
        ).is_ready()

    def status(
        self
    ) -> SUTStatus:
        payload = self._get_json('/health')
        if payload is None:
            return SUTStatus(
                state=UNREACHABLE,
                detail='remote monitor agent is unreachable',
            )
        return self._parse_status(payload)

    def collect_failure_evidence(
        self
    ) -> SUTStatus:
        status = self.status()
        logs = self._get_logs()
        if logs and not status.logs:
            status.logs = logs
        return status

    def _parse_status(
        self,
        payload: dict[str, Any]
    ) -> SUTStatus:
        state = str(
            payload.get('status')
            or payload.get('state')
            or ''
        ).upper()
        process_running = payload.get('process_running')
        if process_running is None:
            process_running = payload.get('running')
        port_listening = payload.get('port_listening')
        if port_listening is None:
            port_listening = payload.get('service_ready')
        returncode = payload.get('returncode')
        if returncode is None:
            returncode = payload.get('exit_code')
        if isinstance(returncode, str):
            try:
                returncode = int(returncode)
            except ValueError:
                returncode = None

        if state not in {RUNNING, EXITED, CRASHED, UNREACHABLE, UNKNOWN}:
            if process_running is True:
                state = RUNNING
            elif process_running is False:
                state = EXITED
            else:
                state = UNKNOWN

        stdout = payload.get('stdout') or ''
        stderr = payload.get('stderr') or ''
        logs = payload.get('logs') or payload.get('log_tail') or ''
        return SUTStatus(
            state=state,
            returncode=returncode,
            stdout=str(stdout),
            stderr=str(stderr),
            logs=str(logs),
            process_running=(
                bool(process_running)
                if process_running is not None
                else None
            ),
            port_listening=(
                bool(port_listening)
                if port_listening is not None
                else None
            ),
            detail=str(payload.get('detail') or ''),
        )

    def _get_logs(
        self
    ) -> str:
        query = parse.urlencode({'tail': self.log_tail})
        payload = self._get_json(f'/logs?{query}')
        if payload is None:
            return ''
        if isinstance(payload, dict):
            return str(payload.get('logs') or payload.get('log_tail') or '')
        return ''

    def _get_json(
        self,
        path: str
    ) -> dict[str, Any] | None:
        try:
            with request.urlopen(
                f'{self.url}{path}',
                timeout=self.timeout_s,
            ) as response:
                raw = response.read()
        except (error.URLError, TimeoutError, OSError) as err:
            logger.debug(f'Executor: remote monitor request failed {path}: {err}')
            return None
        try:
            payload = json.loads(raw.decode('utf-8'))
        except Exception as err:
            logger.debug(f'Executor: remote monitor invalid JSON {path}: {err}')
            return None
        if not isinstance(payload, dict):
            return None
        return payload

    def _post_optional(
        self,
        path: str
    ) -> None:
        req = request.Request(
            f'{self.url}{path}',
            method='POST',
        )
        try:
            with request.urlopen(req, timeout=self.timeout_s):
                return
        except (error.HTTPError, error.URLError, TimeoutError, OSError) as err:
            logger.debug(f'Executor: remote monitor optional POST failed {path}: {err}')


def build_sut_monitor(
    configs
) -> SUTMonitor:
    host = getattr(configs, 'host', 'localhost')
    port = int(getattr(configs, 'port', 0))
    trans_layer = getattr(configs, 'trans_layer', 'tcp')
    monitor_config = getattr(configs, 'monitor', {}) or {}
    mode = str(monitor_config.get('mode', 'none'))
    if mode == 'agent' and monitor_config.get('url'):
        return AgentSUTMonitor(
            url=str(monitor_config['url']),
            host=str(monitor_config.get('service_host') or host),
            port=int(monitor_config.get('service_port') or port),
            trans_layer=str(trans_layer),
            timeout_s=float(monitor_config.get('timeout_s', 1.0)),
            log_tail=int(monitor_config.get('log_tail', 200)),
        )
    return NoopSUTMonitor(
        host=str(host),
        port=port,
        trans_layer=str(trans_layer),
    )
