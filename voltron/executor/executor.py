import subprocess
from pathlib import Path
import time, select, socket, pickle, json, base64, hashlib, asyncio, ast, traceback
from typing import Callable, Tuple

from voltron.configs import configs
from voltron.utils.logger import (
    format_boundary,
    format_event,
    logger_fuzz as logger,
)
from voltron.utils.result_layout import diagnostics_path
from voltron.executor.mapper import Mapper, RuntimeComponentRepairError
from voltron.synthesizer.synthesizer import Generator, Parser
from voltron.synthesizer.checker import Checker
from voltron.synthesizer.observer import ResponseObserver
from voltron.analyzer.analyzer import analyzer
from voltron.executor.conversation import Conversation
from voltron.executor.pair_recorder import RequestResponsePairRecorder
from voltron.executor.response_framing import split_response_frames
from voltron.executor.response_plausibility import classify_response_plausibility
from voltron.executor.sut_monitor import (
    CRASHED,
    EXITED,
    RUNNING,
    UNREACHABLE,
    RemoteSUTProcess,
    build_sut_monitor,
)
import math, statistics, threading, sys, os, signal, re
from dataclasses import dataclass, asdict

CRASH_SIGNALS = {-6, -11, -4, -8}
CRASH_EXIT_CODES = {128 + abs(sig) for sig in CRASH_SIGNALS}
PARSER_FAILURE_RESPONSE = b'PARSE_FAILURE'
ASAN_CRASH_MARKERS = (
    'ERROR: AddressSanitizer',
    'AddressSanitizer:',
    'SUMMARY: AddressSanitizer',
    'LeakSanitizer',
    'UndefinedBehaviorSanitizer',
    'Sanitizer CHECK failed',
    'DEADLYSIGNAL',
)
RUNTIME_EXCEPTION_PATTERNS = (
    # Python
    re.compile(r'Traceback \(most recent call last\):', re.IGNORECASE),
    re.compile(r'Fatal Python error:', re.IGNORECASE),
    re.compile(r'unhandled exception in (?:asyncio|thread)', re.IGNORECASE),
    # Java and other JVM languages
    re.compile(r'Exception in thread "[^"]+"', re.IGNORECASE),
    re.compile(
        r'A fatal error has been detected by the Java Runtime Environment',
        re.IGNORECASE,
    ),
    re.compile(r'Internal Error \(.*\), pid=\d+, tid=\d+', re.IGNORECASE),
    # .NET and Mono (C#, F#, VB.NET)
    re.compile(r'(?:^|\n)\s*Unhandled exception\.', re.IGNORECASE),
    re.compile(r'(?:^|\n)\s*Unhandled Exception:', re.IGNORECASE),
    re.compile(r'FATAL UNHANDLED EXCEPTION:', re.IGNORECASE),
    # Other managed runtimes with equivalent uncaught-failure behavior
    re.compile(r'(?:^|\n)\s*panic:', re.IGNORECASE),
    re.compile(r"thread '[^']+' panicked at", re.IGNORECASE),
    re.compile(r'(?:uncaught exception|uncaught \w*error)', re.IGNORECASE),
    re.compile(r'PHP Fatal error:', re.IGNORECASE),
)


@dataclass(frozen=True)
class CheckerEvaluation:
    status: str
    scope: str
    component_type: str | None
    error: str = ''


@dataclass(frozen=True)
class ObservationResult:
    semantic_fingerprint: str
    raw_fingerprint: str
    scope: str
    component_type: str | None
    provisional: bool
    error: str = ''


@dataclass(frozen=True)
class LifecycleCommandResult:
    stage: str
    success: bool
    returncode: int | None
    duration_s: float
    stdout: str = ''
    stderr: str = ''
    error: str = ''

class Executor:
    """Executor for interacting with the SUT, sending requests and receiving responses, and recording the conversation.
    
    Attributes:
        pre_script: A Path object representing the script to be executed before interacting with the SUT, used for setup.
        post_script: A Path object representing the script to be executed after interacting with the SUT, used for cleanup.
        cmdline: A list of strings representing the command line arguments to execute the SUT.
        host: The hostname or IP address of the SUT to connect to.
        port: The port number on which the SUT is listening for connections.
    """
    def __init__(
            self,
            mapper: Mapper,
            stop_event: threading.Event,
            cmdline: list[str],
            setup_time_s:float = 0.1,
            send_time_ms:int = 1000,
            recv_time_ms:int = 1000
        ) -> None:

        # some attributes for sut
        self.run_script: Path = configs.run_script
        self.setup_script: Path = configs.setup_script
        self.readiness_script: Path | None = getattr(
            configs,
            'readiness_script',
            None,
        )
        self.readiness_adapter = getattr(configs, 'readiness_adapter', '')
        self.setup_timeout_s = getattr(configs, 'setup_timeout_s', 30.0)
        self.socket_readiness_timeout_s = getattr(
            configs, 'socket_readiness_timeout_s', 10.0,
        )
        self.socket_readiness_poll_interval_s = getattr(
            configs, 'socket_readiness_poll_interval_s', 0.1,
        )
        self.readiness_timeout_s = getattr(
            configs,
            'readiness_timeout_s',
            5.0,
        )
        self.protocol_readiness_successes = getattr(
            configs, 'protocol_readiness_successes', 1,
        )
        self.port_release_timeout_s = getattr(
            configs,
            'port_release_timeout_s',
            3.0,
        )
        self.cmdline: list[str] = cmdline
        self.host = configs.host
        self.port = configs.port
        self.trans_layer = configs.trans_layer
        # Kamailio's SIP seeds advertise 127.0.0.1:5061 in Via/Contact.
        # Bind the UDP client socket to that port so replies return to the
        # executor instead of being sent to an unrelated ephemeral port.
        self.local_port = (
            5061
            if self.trans_layer == 'udp'
            and getattr(configs, 'target_name', '') == 'kamailio'
            else None
        )
        self.sut_deployment = getattr(configs, 'sut_deployment', 'local')
        self.sut_monitor = build_sut_monitor(configs)
        self.try_times_parser = 2

        # time related values
        self.setup_time_s = setup_time_s
        self.recv_time_ms = -1
        self.send_time_ms = send_time_ms
        self.max_timeout_ms = 3000
        self.probe_times = 5 # for estimating suitable response time
        self.probe_recv_time_s = []
       
        self.mapper = mapper # mapper between symbol and message
        self.analyzer = analyzer # runtime analyzer
        self.crash_testcases: dict[str, list[bytes]] = {}
        self.unable_parse_request: set[str] = set()
        self._saved_seed_digests: set[str] = set()
        self._saved_seed_lock = threading.Lock()
        self.pair_recorder = RequestResponsePairRecorder(
            getattr(configs, 'results_path', configs.base_path)
        )

        self.parser_func: Callable
        self._parser_code = ''
        self._parser_version = ''
        self._last_known_good_parser: tuple[Callable, str, str] | None = None
        self.parser_degraded = False
        self.parser_fallback_count = 0
        self._parser_ignored_inputs: set[tuple[str, str]] = set()
        self.load_parser(self.mapper.cur_parser)
        self.checker_funcs: dict[str, Callable[[bytes], bool]] = {}
        self.checker_sources: dict[str, str] = {}
        self.observer_funcs: dict[str, Callable[[bytes], str]] = {}
        self.observer_sources: dict[str, tuple[str, str]] = {}
        if configs.fuzz_mode != 'replay':
            self.load_checkers(self.mapper.equip_checkers())
            if getattr(configs, 'observer_enabled', True):
                self.load_observers(self.mapper.equip_observers())
        # Checker/compliance work is budgeted once per parsed response code.
        # Raw request/response pairs are recorded independently.
        self.checked_request_response_pairs: set[str] = set()
        self.reviewed_invalid_responses: set[str] = set()
        self.checked_response_samples: dict[
            tuple[str, str, str], bytes
        ] = {}
        self.reviewed_response_samples: dict[
            tuple[str, str, str], bytes
        ] = {}
        self.observer_evolution_failures: set[tuple[str, ...]] = set()
        self.observer_semantic_reviews: dict[
            tuple[str, str, str], bool
        ] = {}
        self.component_evidence: dict[tuple[str, str, str], dict] = {}
        self._component_usage_lock = threading.Lock()
        self._component_repair_lock = threading.Lock()
        self._component_repair_pending: set[tuple[str, str, str]] = set()
        self._component_usage_counts: dict[str, dict[str, int]] = {
            'checker_status': {},
            'checker_scope': {},
            'observer_scope': {},
        }
        self._component_observed_types: set[str] = set()
        self._component_provisional_count = 0
        self._invalid_response_lock = threading.Lock()
        self._environment_condition = threading.Condition(threading.RLock())
        self._lifecycle_record_lock = threading.Lock()
        self.environment_state = 'not_started'
        self.environment_result: LifecycleCommandResult | None = None
        self.last_readiness_result: LifecycleCommandResult | None = None
        self._interaction_index = 0
        self._active_interaction_proc: subprocess.Popen | None = None
        self._active_interaction_socket: socket.socket | None = None
        self._active_interaction_remote = False
        self._active_interaction_lock = threading.RLock()
        self._prefetched_initial_response: bytes | None = None
        self.stop_event = stop_event
        self.run_controller = getattr(configs, 'run_controller', None)

    def _request_stop(self, reason: str) -> None:
        runtime_analyzer = self._runtime_analyzer()
        request_stop = getattr(runtime_analyzer, 'request_stop', None)
        if callable(request_stop):
            request_stop(reason, self.stop_event)
        else:
            self.stop_event.set()

    def _runtime_analyzer(self):
        """Return the runtime analyzer, including lightweight test doubles."""
        return getattr(self, 'analyzer', analyzer)

    def _increment_lifecycle_metric(self, name: str, value: int = 1) -> None:
        runtime_analyzer = self._runtime_analyzer()
        with runtime_analyzer.lock:
            setattr(
                runtime_analyzer,
                name,
                getattr(runtime_analyzer, name, 0) + value,
            )

    def _record_ready_latency(self, latency_ms: float) -> None:
        runtime_analyzer = self._runtime_analyzer()
        with runtime_analyzer.lock:
            runtime_analyzer.sut_ready_latency_last_ms = latency_ms
            runtime_analyzer.sut_ready_latency_max_ms = max(
                getattr(runtime_analyzer, 'sut_ready_latency_max_ms', 0.0),
                latency_ms,
            )
            samples = getattr(
                runtime_analyzer, 'sut_ready_latency_samples_ms', None,
            )
            if samples is None:
                samples = []
                runtime_analyzer.sut_ready_latency_samples_ms = samples
            samples.append(latency_ms)
            del samples[:-256]

    def _should_stop(self) -> bool:
        """Check the shared deadline before beginning or extending I/O."""
        controller = getattr(self, 'run_controller', None)
        should_stop = getattr(controller, 'should_stop', None)
        if callable(should_stop) and should_stop():
            return True
        return self.stop_event.is_set()

    def _consume_interaction_provenance(
        self,
        msg_seq: list[tuple[str, bytes]],
    ) -> list[dict[str, str]]:
        mapper = getattr(self, 'mapper', None)
        consume = getattr(mapper, 'consume_message_provenance', None)
        if not callable(consume):
            return []
        try:
            return consume(msg_seq)
        except Exception:
            logger.exception('Executor: component provenance lookup failed')
            return []

    def _set_state_snapshot_components(
        self,
        components: list[dict[str, str]],
        request_type: str,
    ) -> None:
        setter = getattr(
            self.analyzer,
            'set_state_snapshot_components',
            None,
        )
        if callable(setter):
            setter(
                components,
                request_type,
                getattr(self, '_parser_version', ''),
            )

    def _poll_with_stop(
        self,
        poller: select.poll,
        timeout_ms: int | float,
    ) -> list[tuple[int, int]] | None:
        """Poll in short slices so a deadline can interrupt socket I/O.

        ``None`` means the run was stopped; an empty list retains the normal
        socket-timeout meaning.
        """
        if self._should_stop():
            return None
        timeout_s = max(0.0, float(timeout_ms) / 1000.0)
        if timeout_s == 0.0:
            return []
        deadline = time.monotonic() + timeout_s
        while True:
            if self._should_stop():
                return None
            remaining_s = deadline - time.monotonic()
            if remaining_s <= 0.0:
                return []
            slice_ms = max(1, min(100, int(remaining_s * 1000)))
            events = poller.poll(slice_ms)
            if events:
                return events
            
    def cov_setup(
        self,
        folder: Path,
        cov_file: Path
    ):
        try:
            proc = subprocess.Popen(
                [configs.cov_setup_path, str(folder), str(cov_file)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            stdout, stderr = proc.communicate()
            logger.debug(f'cov setup: {proc.returncode} {str(stdout)} {str(stderr)}')
            return proc
        except Exception as e:
            logger.debug(f'[SUT Setup Failure]: {e}')
            return None
    
    def cov_collect(
        self,
        folder: Path,
        cov_file: Path,
        file_path: Path
    ):
        try:
            proc = subprocess.Popen(
                [configs.cov_collect_path, str(folder), str(cov_file), str(file_path)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            stdout, stderr = proc.communicate()
            logger.debug(f'cov collect: {proc.returncode} {str(stdout)} {str(stderr)}')
            return proc
        except Exception as e:
            logger.debug(f'[SUT Setup Failure]: {e}')
            return None

    def _environment_sync(self) -> threading.Condition:
        condition = getattr(self, '_environment_condition', None)
        if condition is None:
            condition = threading.Condition(threading.RLock())
            self._environment_condition = condition
        if not hasattr(self, 'environment_state'):
            self.environment_state = 'not_started'
            self.environment_result = None
        return condition

    def _record_lifecycle_event(self, record: dict) -> None:
        results_path = getattr(configs, 'results_path', None)
        if not isinstance(results_path, Path) or not results_path.is_dir():
            return
        lock = getattr(self, '_lifecycle_record_lock', None)
        if lock is None:
            lock = threading.Lock()
            self._lifecycle_record_lock = lock
        payload = {'timestamp': time.time(), **record}
        try:
            with lock:
                target = diagnostics_path(
                    results_path, 'events', 'executor_lifecycle.jsonl'
                )
                target.parent.mkdir(parents=True, exist_ok=True)
                with target.open('a', encoding='utf-8') as stream:
                    json.dump(payload, stream, ensure_ascii=False)
                    stream.write('\n')
        except Exception:
            logger.exception('Executor: failed to persist lifecycle event')

    @staticmethod
    def _bounded_output(value: str | bytes | None, limit: int = 16000) -> str:
        if value is None:
            return ''
        if isinstance(value, bytes):
            value = value.decode('utf-8', errors='backslashreplace')
        return value[-limit:]

    def _run_lifecycle_script(
        self,
        script: Path,
        args: list[str],
        timeout_s: float,
        stage: str,
        env: dict[str, str] | None = None,
    ) -> LifecycleCommandResult:
        started = time.perf_counter()
        proc = None
        try:
            proc = subprocess.Popen(
                [str(script), *args],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                start_new_session=True,
                env=env,
            )
            try:
                stdout, stderr = proc.communicate(timeout=timeout_s)
            except subprocess.TimeoutExpired:
                self._terminate_process_group(
                    proc,
                    signal.SIGTERM,
                    timeout=1,
                )
                stdout, stderr = proc.communicate()
                return LifecycleCommandResult(
                    stage=(
                        f'{stage[:-7]}-timeout'
                        if stage.endswith('-failed')
                        else f'{stage}-timeout'
                    ),
                    success=False,
                    returncode=proc.returncode,
                    duration_s=time.perf_counter() - started,
                    stdout=self._bounded_output(stdout),
                    stderr=self._bounded_output(stderr),
                    error=f'exceeded {timeout_s:.2f}s timeout',
                )
            return LifecycleCommandResult(
                stage=stage,
                success=proc.returncode == 0,
                returncode=proc.returncode,
                duration_s=time.perf_counter() - started,
                stdout=self._bounded_output(stdout),
                stderr=self._bounded_output(stderr),
                error=(
                    ''
                    if proc.returncode == 0
                    else f'exited with status {proc.returncode}'
                ),
            )
        except Exception as error:
            if proc is not None:
                self._terminate_process_group(
                    proc,
                    signal.SIGKILL,
                    timeout=1,
                )
            return LifecycleCommandResult(
                stage=stage,
                success=False,
                returncode=getattr(proc, 'returncode', None),
                duration_s=time.perf_counter() - started,
                error=f'{type(error).__name__}: {error}',
            )

    def initialize_environment(self) -> bool:
        """Run the local setup hook exactly once for this Executor."""
        condition = self._environment_sync()
        with condition:
            while self.environment_state == 'running':
                condition.wait()
            if self.environment_state == 'succeeded':
                return True
            if self.environment_state == 'failed':
                return False
            self.environment_state = 'running'

        remote = self._is_remote_deployment()
        setup_script = getattr(self, 'setup_script', Path())
        should_skip = (
            remote
            or getattr(configs, 'fuzz_mode', '') == 'replay'
            or not setup_script.is_file()
        )
        if should_skip:
            result = LifecycleCommandResult(
                stage='environment-setup-skipped',
                success=True,
                returncode=None,
                duration_s=0.0,
            )
        else:
            result = self._run_lifecycle_script(
                setup_script,
                [],
                getattr(self, 'setup_timeout_s', 30.0),
                'environment-setup-failed',
            )
            if result.success:
                result = LifecycleCommandResult(
                    stage='environment-setup-complete',
                    success=True,
                    returncode=result.returncode,
                    duration_s=result.duration_s,
                    stdout=result.stdout,
                    stderr=result.stderr,
                )

        with condition:
            self.environment_result = result
            self.environment_state = (
                'succeeded' if result.success else 'failed'
            )
            condition.notify_all()

        logger.debug(format_event(
            'environment.initialize',
            stage=result.stage,
            success=result.success,
            script=str(setup_script),
            returncode=result.returncode,
            duration_s=round(result.duration_s, 3),
            stdout=result.stdout,
            stderr=result.stderr,
            error=result.error,
        ))
        self._record_lifecycle_event({
            'event': 'environment.initialize',
            'script': str(setup_script),
            'result': asdict(result),
        })
        if not result.success:
            self._request_stop('sut_failure')
        return result.success

    def setup_exe(self) -> bool:
        """Compatibility alias for the synchronous one-time initialization."""
        return self.initialize_environment()

    def run_exe(
        self
    ) -> subprocess.Popen | None:
        if not self.run_script.is_file():
            logger.debug(
                'Executor: SUT launch failed before Popen: '
                f'run script does not exist or is not a file; '
                f'script={self.run_script}'
            )
            return None

        fuzz_mode = getattr(configs, 'fuzz_mode', '')
        server_mode = getattr(configs, 'server', None)
        if fuzz_mode != 'replay' and server_mode not in {'parent', 'child'}:
            logger.debug(
                'Executor: SUT launch failed before Popen: '
                f'unsupported server mode={server_mode!r}; '
                f'script={self.run_script}'
            )
            return None

        try:
            proc = subprocess.Popen(
                [self.run_script],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                start_new_session=True
            )
            analyzer.sut_proc = proc
            logger.debug(
                f'Executor: launched SUT pid={proc.pid} '
                f'script={self.run_script}'
            )
            return proc
        except Exception as e:
            logger.debug(
                'Executor: SUT launch failed during Popen: '
                f'script={self.run_script}; '
                f'executable={os.access(self.run_script, os.X_OK)}; '
                f'exception={type(e).__name__}: {e}'
            )
            return None

    def _wait_for_port_release(self, port: int) -> bool:
        deadline = time.monotonic() + getattr(
            self,
            'port_release_timeout_s',
            3.0,
        )
        while time.monotonic() < deadline:
            _, listeners_found = self._find_listener_pids(port)
            if not listeners_found:
                return True
            if self.stop_event.wait(0.05):
                return False
        _, listeners_found = self._find_listener_pids(port)
        return not listeners_found

    def start_sut_for_interaction(
        self,
        *,
        stop_on_failure: bool = True,
    ) -> tuple[bool, subprocess.Popen | None]:
        """Start only the per-interaction SUT process."""
        if self._should_stop():
            return False, None
        if self._is_remote_deployment():
            self._monitor().start()
            return True, None

        self.kill_listeners(self.port)
        if not self._wait_for_port_release(self.port):
            self._log_sut_start_failure(
                None,
                stage='sut-cleanup-failed',
                detail='target port remained occupied after listener cleanup',
            )
            if stop_on_failure:
                self._request_stop('sut_failure')
            return False, None

        grace_s = max(0.01, min(0.5, self.setup_time_s))
        proc = None
        for attempt in range(1, 101):
            proc = self.run_exe()
            if proc is None:
                self._log_sut_start_failure(
                    None,
                    stage='sut-launch-failed',
                    attempt=attempt,
                    detail='run_exe returned no process',
                )
                if stop_on_failure:
                    self._request_stop('sut_failure')
                return False, None
            if self.stop_event.wait(grace_s):
                self._terminate_process_group(proc, signal.SIGTERM, timeout=1)
                return False, None
            if proc.poll() is None:
                return True, proc
            self._log_sut_start_failure(
                proc,
                stage='sut-exited-immediately',
                attempt=attempt,
                detail=f'process exited within {grace_s:.2f}s',
            )
            if attempt < 100:
                self._wait_for_port_release(self.port)

        if stop_on_failure:
            self._request_stop('sut_failure')
        return False, proc

    def _wait_for_socket_readiness(
        self,
        proc: subprocess.Popen | None,
    ) -> socket.socket | None:
        remote = self._is_remote_deployment()
        timeout_s = max(0.01, float(getattr(
            self, 'socket_readiness_timeout_s', 10.0,
        )))
        poll_interval_s = max(
            0.01, float(getattr(
                self, 'socket_readiness_poll_interval_s', 0.1,
            )),
        )
        deadline = time.monotonic() + timeout_s
        attempt = 0
        while attempt == 0 or time.monotonic() < deadline:
            attempt += 1
            if self.stop_event.wait(min(poll_interval_s, max(
                0.0, deadline - time.monotonic(),
            ))):
                return None
            sock = self.setup_socket()
            if sock is not None:
                return sock
            if remote:
                status = self._monitor().status()
                if status.state in {EXITED, CRASHED}:
                    self._log_sut_start_failure(
                        proc,
                        stage='remote-readiness-check',
                        attempt=attempt,
                        detail=self._remote_status_summary(),
                    )
                    return None
            elif proc is None or proc.poll() is not None:
                self._increment_lifecycle_metric(
                    'sut_exited_before_first_send',
                )
                self._log_sut_start_failure(
                    proc,
                    stage='sut-exited-before-socket-ready',
                    attempt=attempt,
                    detail='process exited before target port accepted a connection',
                )
                return None

        self._log_sut_start_failure(
            proc,
            stage='socket-readiness-timeout',
            attempt=attempt,
            detail=f'service did not become reachable within {timeout_s:.2f}s',
        )
        self._increment_lifecycle_metric('socket_readiness_timeouts')
        return None

    @staticmethod
    def _ftp_reply_complete(buffer: bytes) -> bool:
        lines = buffer.splitlines(keepends=True)
        if not lines or not lines[0].endswith((b'\n', b'\r')):
            return False
        first = lines[0]
        if len(first) < 4 or not first[:3].isdigit():
            return True
        if first[3:4] != b'-':
            return True
        terminator = first[:3] + b' '
        return any(
            line.startswith(terminator) and line.endswith((b'\n', b'\r'))
            for line in lines[1:]
        )

    def _read_ftp_banner_from_active_socket(
        self,
        sock: socket.socket,
        timeout_s: float,
    ) -> bytes:
        """Read one FTP greeting without opening or modifying the session."""
        if sock is None or sock.fileno() < 0:
            raise ConnectionError('active fuzz socket is unavailable')

        deadline = time.monotonic() + timeout_s
        buffer = b''
        poller = select.poll()
        poller.register(
            sock,
            select.POLLIN | select.POLLERR | select.POLLHUP,
        )
        try:
            while time.monotonic() < deadline:
                if self._should_stop():
                    raise InterruptedError('fuzzing stopped during FTP readiness')
                remaining_ms = max(
                    1,
                    int((deadline - time.monotonic()) * 1000),
                )
                events = self._poll_with_stop(poller, remaining_ms)
                if events is None:
                    raise InterruptedError('fuzzing stopped during FTP readiness')
                if not events:
                    continue
                _fd, event = events[0]
                if event & select.POLLIN:
                    try:
                        chunk = sock.recv(4096)
                    except BlockingIOError:
                        continue
                    if not chunk:
                        raise ConnectionError(
                            'FTP connection closed before a complete banner'
                        )
                    buffer += chunk
                    if len(buffer) > 65536:
                        raise ValueError('FTP banner exceeds 65536 bytes')
                    if self._ftp_reply_complete(buffer):
                        break
                elif event & (select.POLLERR | select.POLLHUP):
                    raise ConnectionError(
                        'FTP socket failed before a complete banner'
                    )
        finally:
            poller.unregister(sock)

        if not self._ftp_reply_complete(buffer):
            raise TimeoutError(
                f'FTP banner was not complete within {timeout_s:.2f}s'
            )
        if (
            not buffer.startswith(b'220')
            or len(buffer) < 4
            or buffer[3:4] not in {b' ', b'-'}
        ):
            raise ValueError(f'invalid FTP banner {buffer!r}')
        return buffer

    def _publish_subject_readiness(
        self,
        result: LifecycleCommandResult,
        source: str,
    ) -> bool:
        self.last_readiness_result = result
        logger.debug(format_event(
            'sut.readiness',
            stage=result.stage,
            success=result.success,
            source=source,
            returncode=result.returncode,
            duration_s=round(result.duration_s, 3),
            stdout=result.stdout,
            stderr=result.stderr,
            error=result.error,
        ))
        self._record_lifecycle_event({
            'event': 'sut.readiness',
            'source': source,
            'host': str(self.host),
            'port': self.port,
            'result': asdict(result),
        })
        return result.success

    def run_subject_readiness(
        self,
        sock: socket.socket | None = None,
        timeout_s: float | None = None,
    ) -> bool:
        """Run a configured protocol readiness check.

        Script hooks use an independent connection.  The ProFTPD adapter is a
        deliberate exception: ``-X`` serves one session and exits, so its FTP
        greeting is consumed from and cached for the active fuzz connection.
        """
        adapter_value = getattr(self, 'readiness_adapter', '')
        adapter = (
            adapter_value.strip()
            if isinstance(adapter_value, str)
            else ''
        )
        timeout_s = (
            getattr(self, 'readiness_timeout_s', 5.0)
            if timeout_s is None else timeout_s
        )
        if adapter:
            started = time.perf_counter()
            try:
                if adapter != 'ftp_banner_active_socket':
                    raise ValueError(f'unknown readiness adapter {adapter!r}')
                banner = self._read_ftp_banner_from_active_socket(
                    sock,
                    timeout_s,
                )
                self._prefetched_initial_response = banner
                result = LifecycleCommandResult(
                    stage='protocol-readiness-complete',
                    success=True,
                    returncode=None,
                    duration_s=time.perf_counter() - started,
                    stdout=self._bounded_output(
                        'FTP banner ready: '
                        + banner.rstrip().decode(
                            'latin-1',
                            errors='replace',
                        )
                    ),
                )
            except Exception as error:
                result = LifecycleCommandResult(
                    stage=(
                        'protocol-readiness-timeout'
                        if isinstance(error, TimeoutError)
                        else 'protocol-readiness-failed'
                    ),
                    success=False,
                    returncode=None,
                    duration_s=time.perf_counter() - started,
                    error=f'{type(error).__name__}: {error}',
                )
            return self._publish_subject_readiness(result, adapter)

        script = getattr(self, 'readiness_script', None)
        if script is None or not script.is_file():
            result = LifecycleCommandResult(
                stage='protocol-readiness-skipped',
                success=True,
                returncode=None,
                duration_s=0.0,
            )
            return self._publish_subject_readiness(result, 'none')

        environment = os.environ.copy()
        environment.update({
            'VOLTRON_READINESS_HOST': str(self.host),
            'VOLTRON_READINESS_PORT': str(self.port),
            'VOLTRON_READINESS_TIMEOUT': str(timeout_s),
        })
        result = self._run_lifecycle_script(
            script,
            [str(self.host), str(self.port), str(timeout_s)],
            timeout_s,
            'protocol-readiness-failed',
            env=environment,
        )
        if result.success:
            result = LifecycleCommandResult(
                stage='protocol-readiness-complete',
                success=True,
                returncode=result.returncode,
                duration_s=result.duration_s,
                stdout=result.stdout,
                stderr=result.stderr,
            )
        return self._publish_subject_readiness(result, str(script))

    def wait_for_subject_readiness(
        self,
        sock: socket.socket | None = None,
    ) -> bool:
        """Require consecutive protocol-readiness successes in one budget."""
        required = max(1, int(getattr(
            self, 'protocol_readiness_successes', 1,
        )))
        # Active-socket adapters consume protocol bytes, so they can only be
        # safely checked once. Target scripts open their own probe socket.
        if getattr(self, 'readiness_adapter', '') and required > 1:
            required = 1
        deadline = time.monotonic() + max(0.01, getattr(
            self, 'readiness_timeout_s', 5.0,
        ))
        consecutive = 0
        while time.monotonic() < deadline and not self._should_stop():
            remaining = max(0.01, deadline - time.monotonic())
            if self.run_subject_readiness(sock, timeout_s=remaining):
                consecutive += 1
                if consecutive >= required:
                    return True
            else:
                consecutive = 0
                self._increment_lifecycle_metric(
                    'protocol_readiness_failures',
                )
            if consecutive < required and self.stop_event.wait(
                min(
                    getattr(self, 'socket_readiness_poll_interval_s', 0.1),
                    remaining,
                )
            ):
                break
        return False

    def _active_lifecycle_lock(self) -> threading.RLock:
        lock = getattr(self, '_active_interaction_lock', None)
        if lock is None:
            lock = threading.RLock()
            self._active_interaction_lock = lock
        return lock

    def _track_active_interaction(
        self,
        proc: subprocess.Popen | None,
        sock: socket.socket | None,
        remote: bool,
    ) -> None:
        with self._active_lifecycle_lock():
            self._active_interaction_proc = proc
            self._active_interaction_socket = sock
            self._active_interaction_remote = remote

    def stop_sut_for_interaction(
        self,
        close_signal: signal.Signals = signal.SIGTERM,
        timeout: float = 3.0,
    ) -> None:
        """Stop only the active interaction socket and target process."""
        with self._active_lifecycle_lock():
            sock = getattr(self, '_active_interaction_socket', None)
            proc = getattr(self, '_active_interaction_proc', None)
            remote = getattr(self, '_active_interaction_remote', False)
            self._active_interaction_socket = None
            self._active_interaction_proc = None
            self._active_interaction_remote = False
            self._prefetched_initial_response = None
        if sock is not None:
            try:
                sock.close()
            except Exception:
                logger.exception('Executor: interaction socket close failed')
        if remote:
            self._monitor().stop()
        else:
            self._terminate_process_group(proc, close_signal, timeout=timeout)
        analyzer.sut_proc = None

    def _log_sut_start_failure(
        self,
        proc: subprocess.Popen | None,
        stage: str,
        attempt: int | None = None,
        detail: str = ''
    ) -> None:
        """Record the available reason for a SUT startup failure."""
        fields = [
            'Executor: SUT startup failure',
            f'stage={stage}',
            f'script={getattr(self, "run_script", "<remote>")}',
            f'transport={self.trans_layer}',
            f'endpoint={getattr(self, "host", "localhost")}:{self.port}',
            f'interaction={getattr(self, "_interaction_index", 0)}',
        ]
        if attempt is not None:
            fields.append(f'attempt={attempt}')
        if detail:
            fields.append(f'detail={detail}')

        process_stdout = ''
        process_stderr = ''
        if proc is None:
            fields.append('process=not-created')
        else:
            return_code = proc.poll()
            fields.append(f'pid={proc.pid}')
            fields.append(
                'process=running'
                if return_code is None
                else f'returncode={return_code}'
            )
            if return_code is not None:
                process_stdout, process_stderr = self._read_process_output(proc)
                if process_stdout:
                    fields.append(f'stdout={process_stdout.strip()!r}')
                if process_stderr:
                    fields.append(f'stderr={process_stderr.strip()!r}')
                if not process_stdout and not process_stderr:
                    fields.append('output=<empty>')

        listener_pids: set[int] = set()
        listener_found: bool | None = None
        try:
            listener_pids, listener_found = self._find_listener_pids(
                self.port
            )
            fields.append(f'port_listening={listener_found}')
            fields.append(
                'listener_pids='
                + (
                    ','.join(str(pid) for pid in sorted(listener_pids))
                    if listener_pids
                    else ('hidden' if listener_found else 'none')
                )
            )
        except Exception as error:
            fields.append(
                f'listener_diagnostic={type(error).__name__}: {error}'
            )

        readiness = getattr(self, 'last_readiness_result', None)
        if readiness is not None:
            fields.extend((
                f'readiness_stage={readiness.stage}',
                f'readiness_returncode={readiness.returncode}',
                f'readiness_stdout={readiness.stdout!r}',
                f'readiness_stderr={readiness.stderr!r}',
                f'readiness_error={readiness.error!r}',
            ))
        environment = getattr(self, 'environment_result', None)
        if environment is not None:
            fields.extend((
                f'environment_stage={environment.stage}',
                f'environment_returncode={environment.returncode}',
                f'environment_stdout={environment.stdout!r}',
                f'environment_stderr={environment.stderr!r}',
                f'environment_error={environment.error!r}',
            ))

        self._record_lifecycle_event({
            'event': 'sut.start_failure',
            'stage': stage,
            'interaction': getattr(self, '_interaction_index', 0),
            'attempt': attempt,
            'detail': detail,
            'script': str(getattr(self, 'run_script', '<remote>')),
            'host': str(getattr(self, 'host', 'localhost')),
            'port': self.port,
            'port_listening': listener_found,
            'listener_pids': sorted(listener_pids),
            'pid': getattr(proc, 'pid', None),
            'returncode': (
                proc.poll() if proc is not None else None
            ),
            'stdout': self._bounded_output(process_stdout),
            'stderr': self._bounded_output(process_stderr),
            'readiness': asdict(readiness) if readiness is not None else None,
            'environment': (
                asdict(environment) if environment is not None else None
            ),
        })

        logger.debug('; '.join(fields))

    def _is_remote_deployment(
        self
    ) -> bool:
        return getattr(self, 'sut_deployment', 'local') == 'remote'

    def _monitor(
        self
    ):
        monitor = getattr(self, 'sut_monitor', None)
        if monitor is None:
            self.sut_monitor = build_sut_monitor(configs)
            monitor = self.sut_monitor
        return monitor

    def _remote_status_summary(
        self
    ) -> str:
        status = self._monitor().status()
        fields = [
            f'remote_state={status.state}',
            f'returncode={status.returncode}',
            f'process_running={status.process_running}',
            f'port_listening={status.port_listening}',
        ]
        if status.detail:
            fields.append(f'detail={status.detail}')
        return '; '.join(fields)

    def interact(
        self,
        msg_seq: list[tuple[str, bytes]],
        poll_wait_ms: int = 5000,
        run_checker: bool = False
    ) -> Tuple[bool, Conversation | None]:
        """Log one complete interaction and execute it against the SUT."""
        interaction_id = f'{time.monotonic_ns():x}'
        request_types = '/'.join(
            msg_type
            for msg_type, _ in msg_seq
        ) or '-'
        started_at = time.perf_counter()
        result: Tuple[bool, Conversation | None] | None = None
        outcome = 'exception'
        error_type = None

        logger.debug(format_boundary(
            'interact.begin',
            interaction_id=interaction_id,
            request_count=len(msg_seq),
            request_types=request_types,
            poll_wait_ms=poll_wait_ms,
            checker_enabled=run_checker,
            mode=getattr(configs, 'fuzz_mode', ''),
            endpoint=(
                f'{getattr(self, "host", "?")}:'
                f'{getattr(self, "port", "?")}'
            ),
        ))
        try:
            result = self._interact_once(
                msg_seq,
                poll_wait_ms=poll_wait_ms,
                run_checker=run_checker,
            )
            flag, conversation = result
            pair_recorder = getattr(self, 'pair_recorder', None)
            if flag and conversation is not None and pair_recorder is not None:
                phase = (
                    getattr(self.analyzer, 'active_phase', None)
                    or getattr(self.analyzer, 'stage', '')
                )
                if isinstance(pair_recorder, RequestResponsePairRecorder):
                    pair_recorder.observe(
                        conversation,
                        phase=phase,
                        component_evidence=getattr(
                            self,
                            'component_evidence',
                            {},
                        ),
                    )
                else:
                    pair_recorder.observe(conversation, phase=phase)
            if flag:
                outcome = 'completed'
            elif self._should_stop():
                outcome = 'stopped'
            else:
                outcome = 'failed'
            return result
        except BaseException as error:
            error_type = type(error).__name__
            outcome = (
                'interrupted'
                if isinstance(error, (KeyboardInterrupt, SystemExit))
                else 'exception'
            )
            raise
        finally:
            self.stop_sut_for_interaction(signal.SIGTERM, timeout=1)
            conversation = result[1] if result is not None else None
            logger.debug(format_boundary(
                'interact.end',
                interaction_id=interaction_id,
                outcome=outcome,
                duration_ms=round(
                    (time.perf_counter() - started_at) * 1000,
                    3,
                ),
                recorded_exchanges=(
                    len(conversation.content)
                    if conversation is not None
                    else 0
                ),
                response_types=(
                    '/'.join(conversation.res_seq)
                    if conversation is not None
                    else '-'
                ),
                error_type=error_type,
            ))

    def _interact_once(
        self,
        msg_seq: list[tuple[str, bytes]],
        poll_wait_ms: int = 5000,
        run_checker: bool = False
    ) -> Tuple[bool, Conversation | None] :  
        """Interact with the SUT by sending a sequence of messages and receiving the corresponding responses, while recording the conversation.
        
        Args:
            msg_seq: A list of tuples, where each tuple contains a string representing the message type and a bytes object representing the message content to be sent to the SUT.
            poll_wait_ms: An integer representing the maximum time in milliseconds to wait for a response from the SUT after sending each message.
            run_checker: Enable response conformance checking. This is only
                enabled by the fuzzing scheduler, not model learning or replay.
        """
        # logger.debug('exe: begin inter')
        # prepare some settings and setup SUT
        remote_deployment = self._is_remote_deployment()
        if self._should_stop():
            return False, None
        if not self.initialize_environment():
            return False, None
        if not hasattr(self, '_interaction_index'):
            self._interaction_index = 0
        self._interaction_index += 1
        self._prefetched_initial_response = None
        component_provenance = self._consume_interaction_provenance(msg_seq)

        retry_limit = max(
            1,
            int(getattr(configs, 'sut_interaction_retry_limit', 3)),
        )
        retry_delay_s = max(
            0.0,
            float(getattr(configs, 'sut_interaction_retry_delay_s', 0.1)),
        )
        proc = None
        sock = None
        for lifecycle_attempt in range(1, retry_limit + 1):
            lifecycle_started = time.monotonic()
            self._increment_lifecycle_metric('sut_launch_attempts')
            if lifecycle_attempt > 1:
                self._increment_lifecycle_metric('sut_lifecycle_retries')
            started, proc = self.start_sut_for_interaction(
                stop_on_failure=False,
            )
            if started:
                self._track_active_interaction(proc, None, remote_deployment)
                sock = self._wait_for_socket_readiness(proc)
            if sock is not None:
                self._track_active_interaction(proc, sock, remote_deployment)
                if self.wait_for_subject_readiness(sock):
                    ready_ms = (time.monotonic() - lifecycle_started) * 1000
                    self._record_ready_latency(ready_ms)
                    break
                if not remote_deployment:
                    self._log_sut_start_failure(
                        proc,
                        stage=(
                            self.last_readiness_result.stage
                            if self.last_readiness_result is not None
                            else 'protocol-readiness-failed'
                        ),
                        attempt=lifecycle_attempt,
                        detail=(
                            self.last_readiness_result.error
                            if self.last_readiness_result is not None
                            else 'protocol readiness hook failed'
                        ),
                    )
            self.stop_sut_for_interaction(signal.SIGTERM, timeout=1)
            sock = None
            if lifecycle_attempt < retry_limit and not self.stop_event.wait(
                retry_delay_s
            ):
                logger.debug(
                    'Executor: retrying transient SUT lifecycle failure '
                    '[attempt=%s/%s]',
                    lifecycle_attempt + 1,
                    retry_limit,
                )
                continue
            break

        if sock is None:
            self._request_stop('sut_failure')
            return False, None
        
        
        logger.debug(">>>Executor: interact start")
        # keep request and response in Conversation
        cons: Conversation = Conversation()
        
        # maybe recv initialize message
        resp_code, resp_data = self._receive_initial_response(
            sock=sock,
            poll_timeout_ms=100,
            show_fuzz_ui=run_checker,
        )
        if self._should_stop():
            self.stop_sut_for_interaction(signal.SIGTERM, timeout=1)
            return False, None
        last_recv = '-'
        if(resp_code and resp_data):
            self._set_state_snapshot_components([], '-')
            is_valid_response = self.check_response_during_fuzzing(
                '-',
                resp_code,
                resp_data,
                run_checker,
            )
            cons.add_state(
                '-',
                self._model_response_symbol(
                    list(getattr(self, '_last_response_frames', [])),
                    resp_code,
                ),
            )
            cons.add_data(bytes(), resp_data)
            if not is_valid_response:
                self.handle_nonconforming_response(cons, resp_code)
            last_recv = resp_code
            with self.analyzer.lock:
                self.analyzer.res_types_update(resp_code)
                self.analyzer.resp_trans_update(f'-/{resp_code}')
        else:
            cons.add_state('-', '-')
            cons.add_data(bytes(), bytes())

        # send the message sequence and parse the response, record the conversation in cons
        last_msg_type = '-'
        last_msg = bytes()
        last_request_recorded = True
        for request_index, (msg_type, msg) in enumerate(msg_seq):
            if self._should_stop():
                break
            
            if not remote_deployment and proc.poll() is not None:
                if not self._handle_crash_if_detected(
                    cons,
                    proc,
                    last_msg_type,
                    last_msg,
                    request_recorded=last_request_recorded,
                ):
                    cons.add_state(msg_type, 'CLOSED')
                    cons.add_data(msg or bytes(), bytes())
                    logger.debug('server close')
                break

            last_msg_type = msg_type
            last_msg = msg if msg is not None else bytes()
            
            # send message and parse response
            if msg == None:
                self.stop_sut_for_interaction(signal.SIGTERM, timeout=1)
                return False, None
            
            flag, req_data = self.net_send(msg, sock)
            
            # success to send
            if(flag and req_data):
                last_request_recorded = False
                logger.debug(format_event(
                    'network.send',
                    request_type=msg_type,
                    length=len(req_data),
                    data=req_data,
                ))
                with self.analyzer.lock:
                    self.analyzer.req_num = self.analyzer.req_num + 1
                    self.analyzer.req_types_update(msg_type)
                resp_code, resp_data = self.net_recv(
                    sock=sock,
                    poll_timeout_ms=poll_wait_ms,
                    msg_type=msg_type,
                    show_fuzz_ui=run_checker,
                )

                if resp_code == 'POLLERR':
                    # crash
                    # normal
                    if not self._handle_crash_if_detected(
                        cons,
                        proc,
                        msg_type,
                        msg,
                        request_recorded=False,
                    ):
                        cons.add_state(msg_type, 'POLLERR')
                        cons.add_data(req_data, bytes())
                        with self.analyzer.lock:
                            self.analyzer.rclose_num += 1
                        logger.debug(f'recv <- POLLERR')
                        last_request_recorded = True
                    break
                
                elif resp_code == 'TIMEOUT':
                    # crash
                    # noraml
                    if not self._handle_crash_if_detected(
                        cons,
                        proc,
                        msg_type,
                        msg,
                        request_recorded=False,
                    ):
                        cons.add_state(msg_type, 'TIMEOUT')
                        cons.add_data(req_data, bytes())
                        with self.analyzer.lock:
                            self.analyzer.timeout_num += 1
                        logger.debug(f'recv <- TIMEOUT')
                        last_request_recorded = True
                    break
                
                elif resp_code == 'RCLOSED':
                    # crash
                    # normal
                    if not self._handle_crash_if_detected(
                        cons,
                        proc,
                        msg_type,
                        msg,
                        request_recorded=False,
                    ):
                        cons.add_state(msg_type, 'CLOSED')
                        cons.add_data(req_data, bytes())
                        with self.analyzer.lock:
                            self.analyzer.rclose_num += 1
                        logger.debug(f'recv <- rclose')
                        last_request_recorded = True
                    break
                
                else:
                    if(resp_code == None):
                        logger.debug('Executor: parse error')
                        continue

                    response_frames = list(getattr(
                        self, '_last_response_frames', [],
                    ))
                    frame_metadata = [{
                        key: value
                        for key, value in frame.items()
                        if key != 'data'
                    } for frame in response_frames]
                    if resp_code == PARSER_FAILURE_RESPONSE.decode():
                        ignored_invalid = bool(response_frames) and all(
                            frame.get('parse_status') == 'ignored_invalid'
                            for frame in response_frames
                        )
                        # Retain the raw receive batch and frame metadata for
                        # offline repair, but never turn a parser failure into
                        # a learned response type or transition.
                        if req_data is not None:
                            cons.add_data(
                                req_data,
                                resp_data or bytes(),
                                response_frames=frame_metadata,
                            )
                        with self.analyzer.lock:
                            self.analyzer.recv_batches = getattr(
                                self.analyzer, 'recv_batches', 0,
                            ) + 1
                            self.analyzer.response_frames = getattr(
                                self.analyzer, 'response_frames', 0,
                            ) + len(response_frames)
                            if len(response_frames) > 1:
                                self.analyzer.multi_frame_requests = getattr(
                                self.analyzer,
                                'multi_frame_requests', 0,
                            ) + 1
                            if ignored_invalid:
                                self.analyzer.ignored_invalid_responses = getattr(
                                    self.analyzer,
                                    'ignored_invalid_responses', 0,
                                ) + 1
                            else:
                                cons.add_state(msg_type, resp_code)
                                self.analyzer.parse_failures = getattr(
                                    self.analyzer, 'parse_failures', 0,
                                ) + 1
                        last_request_recorded = True
                        continue

                    self._set_state_snapshot_components(
                        component_provenance[:request_index + 1],
                        msg_type,
                    )

                    is_valid_response = True
                    if resp_data is not None:
                        is_valid_response = self.check_response_during_fuzzing(
                            msg_type,
                            resp_code,
                            resp_data,
                            run_checker,
                        )
                    
                    semantic_frames = [frame for frame in response_frames if frame[
                        'parse_status'
                    ] == 'parsed']
                    if not semantic_frames:
                        semantic_frames = [{
                            'response_type': resp_code,
                            'data': resp_data or bytes(),
                        }]
                    with self.analyzer.lock:
                        self.analyzer.recv_batches = getattr(
                            self.analyzer, 'recv_batches', 0,
                        ) + 1
                        self.analyzer.response_frames = getattr(
                            self.analyzer, 'response_frames', 0,
                        ) + len(semantic_frames)
                        if len(semantic_frames) > 1:
                            self.analyzer.multi_frame_requests = getattr(
                                self.analyzer, 'multi_frame_requests', 0,
                            ) + 1
                        for frame in semantic_frames:
                            frame_type = frame['response_type']
                            self.analyzer.res_num += 1
                            self.analyzer.res_types_update(frame_type)
                            self.analyzer.resp_trans_update(
                                f'{last_recv}/{frame_type}'
                            )
                            last_recv = frame_type
                    logger.debug(format_event(
                        'network.receive',
                        request_type=msg_type,
                        response_type=resp_code,
                        length=(
                            len(resp_data)
                            if resp_data is not None
                            else 0
                        ),
                        data=resp_data,
                    ))
                    
                    # record conversation data
                    if req_data is not None:
                        cons.add_data(
                            req_data,
                            resp_data or bytes(),
                            response_frames=frame_metadata,
                        )
                    cons.add_state(
                        msg_type,
                        self._model_response_symbol(response_frames, resp_code),
                    )
                    last_request_recorded = True
                    if not is_valid_response:
                        self.handle_nonconforming_response(cons, resp_code)
            
            # If socket closed, stop sending
            else:
                return_code = proc.poll() if proc is not None else None
                
                # program exited unexpectly
                self._handle_crash_if_detected(
                    cons,
                    proc,
                    msg_type,
                    msg,
                    request_recorded=False,
                )
                        
                seq = '/'.join([msg_type for msg_type, data in msg_seq])
                logger.debug(f'Executor: socket closed with {return_code} because of {seq}')
                break

        with self.analyzer.lock:
            self.analyzer.path_num = self.analyzer.path_num + 1

        self._handle_crash_if_detected(
            cons,
            proc,
            last_msg_type,
            last_msg,
            request_recorded=last_request_recorded,
        )
        
        # close process
        close_signal = (
            signal.SIGUSR1
            if getattr(configs, 'fuzz_mode', '') == 'replay'
            else signal.SIGTERM
        )
        self.stop_sut_for_interaction(close_signal, timeout=3)
        
        # ensure sub-subprocess die
        # if proc.poll is None:
        #     while True:
        #         try:
        #             os.killpg(proc.pid, 0)
        #             # no die, just kill
        #             time.sleep(0.1)
        #             os.killpg(proc.pid, signal.SIGKILL)
        #             logger.debug(f'try to kill: {proc.pid}')
        #         except Exception as e:
        #             # sub-subprocess die out
        #             analyzer.sut_proc = None
        #             logger.debug(f'target process: {e}')
        #             break
        
        # self.post_exe()
        logger.debug("<<<Executor: interact done")
        return True, cons

    def _terminate_process_group(
        self,
        proc: subprocess.Popen | None,
        sig: signal.Signals,
        timeout: float
    ) -> None:
        """Terminate a SUT process tree that was started with start_new_session."""
        if proc is None:
            return
        try:
            if proc.poll() is None:
                os.killpg(proc.pid, sig)
                returncode = proc.wait(timeout=timeout)
                logger.debug(f'close process group [returncode: {returncode} pid: {proc.pid}]')
                return
        except subprocess.TimeoutExpired:
            logger.debug(f'process group did not stop after {sig.name}: {proc.pid}')
        except ProcessLookupError:
            logger.debug(f'process group already closed: {proc.pid}')
            return
        except Exception as err:
            logger.debug(f'process group close err: {err}')

        try:
            if proc.poll() is None:
                os.killpg(proc.pid, signal.SIGKILL)
                returncode = proc.wait(timeout=1)
                logger.debug(f'killed process group [returncode: {returncode} pid: {proc.pid}]')
        except Exception as err:
            logger.debug(f'process group kill err: {err}')
    
    def kill_listeners(
        self,
        port: int
    ) -> None:
        """Kill processes listening on exactly the requested TCP/UDP port."""
        pids, listeners_found = self._find_listener_pids(port)
        if not listeners_found:
            return
        if not pids:
            logger.debug(
                'Executor: listener found but PID is unavailable; '
                f'port={port}; check process visibility and privileges'
            )
            return

        for pid in sorted(pids):
            if pid <= 1 or pid == os.getpid():
                logger.debug(
                    'Executor: refusing to kill unsafe listener PID; '
                    f'port={port}; pid={pid}'
                )
                continue

            try:
                logger.debug(
                    f'Executor: killing listener port={port}; pid={pid}'
                )
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                logger.debug(
                    'Executor: listener exited before kill; '
                    f'port={port}; pid={pid}'
                )
                continue
            except PermissionError as e:
                logger.debug(
                    'Executor: permission denied while killing listener; '
                    f'port={port}; pid={pid}; error={e}'
                )
                continue
            except Exception as e:
                logger.debug(
                    'Executor: failed to kill listener; '
                    f'port={port}; pid={pid}; '
                    f'exception={type(e).__name__}: {e}'
                )
                continue

            if self._wait_for_process_exit(pid, timeout=0.5):
                logger.debug(
                    f'Executor: listener stopped port={port}; pid={pid}'
                )
            else:
                logger.debug(
                    'Executor: listener still exists after SIGKILL; '
                    f'port={port}; pid={pid}; '
                    'possible uninterruptible sleep or PID visibility issue'
                )

        remaining_pids, remaining_found = self._find_listener_pids(port)
        if remaining_found:
            logger.debug(
                'Executor: port remains occupied after listener cleanup; '
                f'port={port}; '
                f'pids={sorted(remaining_pids) if remaining_pids else "hidden"}; '
                'the service may be supervised or automatically restarted'
            )

    def _find_listener_pids(
        self,
        port: int
    ) -> tuple[set[int], bool]:
        """Find listener PIDs with ss, falling back to netstat."""
        commands = (
            ('ss', ['ss', '-H', '-ltnup']),
            ('netstat', ['netstat', '-tulnp']),
        )
        failures = []

        for tool, command in commands:
            try:
                result = subprocess.run(
                    command,
                    capture_output=True,
                    text=True,
                    check=False,
                )
            except FileNotFoundError:
                failures.append(f'{tool}=not-found')
                continue
            except Exception as e:
                failures.append(
                    f'{tool}={type(e).__name__}: {e}'
                )
                continue

            if result.returncode != 0:
                reason = result.stderr.strip() or result.stdout.strip()
                failures.append(
                    f'{tool}=exit-{result.returncode}: '
                    f'{reason or "no diagnostic output"}'
                )
                continue
            if result.stderr.strip() and not result.stdout.strip():
                failures.append(
                    f'{tool}=no-output: {result.stderr.strip()}'
                )
                continue

            pids, listeners_found = self._parse_listener_output(
                result.stdout,
                port,
                tool,
            )
            if listeners_found and not pids:
                diagnostic = result.stderr.strip()
                if diagnostic:
                    logger.debug(
                        'Executor: listener query could not expose PID; '
                        f'tool={tool}; port={port}; '
                        f'diagnostic={diagnostic!r}'
                    )
            return pids, listeners_found

        logger.debug(
            'Executor: unable to inspect port listeners; '
            f'port={port}; reasons={"; ".join(failures)}'
        )
        return set(), False

    def _parse_listener_output(
        self,
        output: str,
        port: int,
        tool: str
    ) -> tuple[set[int], bool]:
        """Parse only lines whose local endpoint exactly matches port."""
        pids: set[int] = set()
        listeners_found = False

        for line in output.splitlines():
            tokens = line.split()
            local_index = 4 if tool == 'ss' else 3
            if len(tokens) <= local_index:
                continue
            local_endpoint = tokens[local_index].rstrip(',')
            port_match = re.search(r':(\d+)$', local_endpoint)
            if port_match is None or int(port_match.group(1)) != port:
                continue

            listeners_found = True
            if tool == 'ss':
                pids.update(
                    int(pid)
                    for pid in re.findall(r'\bpid=(\d+)', line)
                )
            elif tool == 'netstat':
                pids.update(
                    int(pid)
                    for pid in re.findall(r'\b(\d+)/[^\s]+', line)
                )

        return pids, listeners_found

    def _wait_for_process_exit(
        self,
        pid: int,
        timeout: float
    ) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                return True
            except PermissionError:
                return False
            time.sleep(0.02)

        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        except PermissionError:
            return False
        return False
        
    def setup_socket(
        self
    ) -> socket.socket | None:
            """Setup the socket for network communication

            Returns:
                socket for sending and receiving
            """
            sock: socket.socket
            
            try:
                if (self.trans_layer == 'tcp'):
                    sock = socket.create_connection((self.host, self.port))
                elif (self.trans_layer == 'udp'):
                    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                    if self.local_port is not None:
                        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                        sock.bind((self.host, self.local_port))
                else:
                    return None
            except ConnectionRefusedError as e:
                logger.debug(f"ConnectionRefusedError {e}. Connect to {self.host}:{self.port}")
                return None
            except PermissionError as e:
                logger.debug(f"PermissionError {e}. Connect to {self.host}:{self.port}")
                return None
            except Exception as e:
                logger.debug(f"Setup Socket Failure {e}. Connect to {self.host}:{self.port}")
                return None
            sock.setblocking(False)
            return sock

    def net_send(
            self, 
            msg : bytes,
            sock: socket.socket
    ) -> Tuple[bool, bytes | None]:
        """Send message over network

        use poll to monitor the status of socket
        """
        if sock is None or sock.fileno() < 0:
            logger.debug("net_send: invalid socket")
            return False, None
        if self._should_stop():
            return False, None
        
        poller = select.poll()
        poller.register(sock, select.POLLOUT | select.POLLERR | select.POLLHUP)
        
        try:
            if (self.trans_layer == 'tcp'):
                
                # handler poll timeout
                events = self._poll_with_stop(poller, self.send_time_ms)
                if events is None:
                    return False, None
                if not events:
                    logger.debug("net_send: poll timeout")
                    return False, None

                fd, event = events[0]

                # handler poll error and hup
                if event & (select.POLLERR):
                    logger.debug("net_send: poll err")
                    return False, None
                
                if event & select.POLLHUP:
                    logger.debug("net_send: poll hup")
                    return False, None

                # send message
                if event & select.POLLOUT:
                    
                    try:
                        sock.sendall(msg)
                    
                    except Exception as err:
                        # socket break when sending
                        logger.debug(f'net_send: socket broken {err} {msg}')
                        return False, None
                    return True, msg
            
            # TODO: support udp
            elif (self.trans_layer == 'udp'):
                events = self._poll_with_stop(poller, self.send_time_ms)
                if events is None:
                    return False, None
                if not events:
                    logger.debug("net_send: poll timeout")
                    return False, None

                fd, event = events[0]
                if event & select.POLLOUT:
                    try:
                        sock.sendto(msg, (self.host, self.port))
                    except Exception as err:
                        # socket break when sending
                        logger.debug(f'net_send: socket broken {msg}')
                        return False, None
                    return True, msg
        finally:
            poller.unregister(sock)

        return False, None
    
    def _parse_tcp_response(
        self,
        buf: bytes,
        msg_type: str,
        show_fuzz_ui: bool,
    ) -> str:
        resp_byte = self._invoke_parser_with_repair(buf, show_fuzz_ui)
        return resp_byte.decode(
            'utf-8',
            errors='backslashreplace',
        )

    @staticmethod
    def _model_response_symbol(
        response_frames: list[dict],
        fallback: str,
    ) -> str:
        """Encode one receive batch as the output of one model input.

        Response accounting stays per frame, but L* requires exactly one
        output symbol per sent request.  A multi-frame batch therefore uses a
        canonical JSON array; one-frame traffic retains its legacy response
        type so existing models and metrics remain comparable.
        """
        semantic = [
            frame.get('response_type')
            for frame in response_frames
            if frame.get('parse_status') == 'parsed'
            and isinstance(frame.get('response_type'), str)
        ]
        if len(semantic) <= 1:
            return semantic[0] if semantic else fallback
        return json.dumps(semantic, ensure_ascii=False, separators=(',', ':'))

    def _parse_response_frames(
        self,
        buf: bytes,
        msg_type: str,
        show_fuzz_ui: bool,
        datagrams: list[dict] | None = None,
    ) -> list[dict]:
        """Parse framed responses while retaining receive-batch provenance."""
        batch_id = getattr(self, '_recv_batch_id', 0) + 1
        self._recv_batch_id = batch_id
        frames = []
        for index, frame in enumerate(split_response_frames(
            getattr(configs, 'pro_name', ''), buf,
        )):
            framing_incomplete = frame.framing_status != 'framed'
            response_type = (
                PARSER_FAILURE_RESPONSE.decode()
                if framing_incomplete
                else self._parse_tcp_response(
                    frame.data, msg_type, show_fuzz_ui,
                )
            )
            parser_failure_status = getattr(
                self, '_last_parser_failure_status', 'parse_failure'
            )
            overlapping_datagrams = [
                datagram for datagram in (datagrams or [])
                if datagram['offset_end'] > frame.offset_start
                and datagram['offset_start'] < frame.offset_end
            ]
            frames.append({
                'recv_batch_id': batch_id,
                'frame_index': index,
                'offset_start': frame.offset_start,
                'offset_end': frame.offset_end,
                'timestamp': time.time(),
                'response_type': response_type,
                'parse_status': (
                    'framing_incomplete'
                    if framing_incomplete
                    else (
                        parser_failure_status
                        if response_type == PARSER_FAILURE_RESPONSE.decode()
                        else 'parsed'
                    )
                ),
                'framing_error': frame.framing_error,
                'datagrams': overlapping_datagrams,
                'data': frame.data,
            })
        self._last_response_frames = frames
        return frames

    @staticmethod
    def _response_batch_result(frames: list[dict]) -> str:
        """Choose the one model output while accounting for every frame."""
        semantic = [
            frame for frame in frames
            if frame['parse_status'] == 'parsed'
        ]
        return (semantic[-1] if semantic else frames[-1])['response_type']

    def _invoke_parser_with_repair(
        self,
        response: bytes,
        show_fuzz_ui: bool,
    ) -> bytes:
        self._last_parser_failure_status = 'parse_failure'
        try:
            parsed = self.parser_func(response)
            if not isinstance(parsed, bytes):
                raise TypeError(
                    'packet_parser must return bytes; '
                    f'got {type(parsed).__name__}'
                )
            if not parsed:
                raise ValueError(
                    'packet_parser returned empty bytes for the runtime response'
                )
            self._last_known_good_parser = (
                self.parser_func,
                getattr(self, '_parser_code', ''),
                getattr(self, '_parser_version', ''),
            )
            return parsed
        except Exception as exception:
            unclassified_response = (
                isinstance(exception, ValueError)
                and str(exception)
                == 'packet_parser returned empty bytes for the runtime response'
            )
            error = (
                f'{type(exception).__name__}: {exception}\n'
                f'{traceback.format_exc()}'
            )
            failed_code = getattr(self, '_parser_code', '')
            failed_version = getattr(self, '_parser_version', 'unknown')

        plausibility = classify_response_plausibility(
            getattr(configs, 'pro_name', ''), response,
        )
        if (
            unclassified_response
            and plausibility.status == 'invalid'
            and response
        ):
            self._last_parser_failure_status = 'ignored_invalid'
            self._record_ignored_parser_input(
                response=response,
                version=failed_version,
                error=error,
                reason=plausibility.reason,
            )
            logger.debug(
                'Executor: ignored implausible parser input '
                '[version=%s input_sha256=%s reason=%s]',
                failed_version,
                hashlib.sha256(response).hexdigest(),
                plausibility.reason,
            )
            return PARSER_FAILURE_RESPONSE

        if show_fuzz_ui:
            self._set_ui_operation('Repairing parser from runtime failure')
        failure_key = (
            failed_version,
            hashlib.sha256(response).hexdigest(),
        )
        failed_inputs = getattr(self, '_parser_failed_inputs', set())
        repair_allowed = failure_key not in failed_inputs
        if repair_allowed:
            failed_inputs.add(failure_key)
            self._parser_failed_inputs = failed_inputs
        try:
            repair = None
            if repair_allowed:
                repair = self.mapper.repair_runtime_component(
                    component='parser',
                    component_type='__all__',
                    version=getattr(self, '_parser_version', 'unknown'),
                    source_code=getattr(self, '_parser_code', ''),
                    error=error,
                    runtime_input=response,
                )
            if repair is not None:
                parser, _code = repair
                self.mapper.cur_parser = parser
                self.load_parser(parser)
                replayed = self.parser_func(response)
                if isinstance(replayed, bytes) and replayed:
                    self._last_known_good_parser = (
                        self.parser_func,
                        self._parser_code,
                        self._parser_version,
                    )
                    logger.debug('Executor: parser repair replay succeeded')
                    return replayed
                error = (
                    'repaired packet_parser failed same-input replay: '
                    f'{type(replayed).__name__} {replayed!r}'
                )

            fallback = getattr(self, '_last_known_good_parser', None)
            if fallback is not None:
                fallback_func, fallback_code, fallback_version = fallback
                if (
                    fallback_version != failed_version
                    or fallback_code != failed_code
                ):
                    replayed = fallback_func(response)
                    if isinstance(replayed, bytes) and replayed:
                        self.parser_func = fallback_func
                        self._parser_code = fallback_code
                        self._parser_version = fallback_version
                        logger.warning(
                            'Executor: rolled parser back to last-known-good %s',
                            fallback_version,
                        )
                        return replayed
        except Exception as repair_error:
            error = (
                f'{error}\nrepair_failure: '
                f'{type(repair_error).__name__}: {repair_error}'
            )
        finally:
            if show_fuzz_ui:
                self._set_ui_operation('')

        if response:
            self.parser_degraded = True
            self.parser_fallback_count = (
                getattr(self, 'parser_fallback_count', 0) + 1
            )
            logger.warning(
                'Executor: parser repair exhausted; using PARSE_FAILURE fallback '
                '[version=%s input_sha256=%s]',
                failed_version,
                hashlib.sha256(response).hexdigest(),
            )
            append_record = getattr(
                self.mapper, '_append_runtime_record', None
            )
            if callable(append_record):
                append_record(
                    'component_parser_fallbacks.jsonl',
                    {
                        'timestamp': time.time(),
                        'component': 'parser',
                        'failed_version': failed_version,
                        'input_sha256': hashlib.sha256(response).hexdigest(),
                        'input_length': len(response),
                        'fallback_response': PARSER_FAILURE_RESPONSE.decode(),
                        'error': error[:12000],
                    },
                )
            return PARSER_FAILURE_RESPONSE

        raise RuntimeComponentRepairError(
            f'parser runtime repair exhausted: {error}'
        )

    def _receive_initial_response(
        self,
        sock: socket.socket,
        poll_timeout_ms: int,
        show_fuzz_ui: bool,
    ) -> Tuple[str | None, bytes | None]:
        prefetched = getattr(self, '_prefetched_initial_response', None)
        self._prefetched_initial_response = None
        if prefetched is None:
            return self.net_recv(
                sock=sock,
                poll_timeout_ms=poll_timeout_ms,
                show_fuzz_ui=show_fuzz_ui,
            )
        frames = self._parse_response_frames(prefetched, '-', show_fuzz_ui)
        return self._response_batch_result(frames), prefetched

    def net_recv(
            self, 
            sock: socket.socket,
            poll_timeout_ms = 0,
            msg_type = '-',
            show_fuzz_ui: bool = False
    ) -> Tuple[str | None, bytes | None]:
        """Recv message over network

        use poll to monitor the status of socket
        """
        # check clinet socket before response
        if sock is None or sock.fileno() < 0:
            logger.debug("Executor: socket closed")
            return None, None
        if self._should_stop():
            return None, None
        
        """ 
        Remote Socket Normal Close (FIN): poll in, recv value 0
        Remote Socket Exception Close (RST): poll error, recv value -1
        Remote Program Hang: recv timeout, no poll event
        """
        poller = select.poll()
        poller.register(sock, select.POLLIN | select.POLLERR)
        
        time_out_ms = 0
        if poll_timeout_ms != 0:
            time_out_ms = poll_timeout_ms
        else:
            time_out_ms = self.max_timeout_ms
        
        try:
            if (self.trans_layer == 'tcp'):
                events = self._poll_with_stop(poller, time_out_ms)
                if events is None:
                    return None, None

                # handler recv timeout
                if not events:
                    logger.debug('recv: poll timeout')
                    return 'TIMEOUT', None
                
                fd, event = events[0]
                
                if event & (select.POLLERR):
                    return 'POLLERR', None
                # response can be read

                if event & select.POLLIN:
                    buf = b''
                    
                    while True:
                        events = self._poll_with_stop(poller, 10)
                        if events is None:
                            return None, None
                        if not events:
                            break
                        chunk = sock.recv(2048)
                        if not chunk:
                            break
                        buf += chunk

                    # logger.debug(f'net_recv: {buf}')
                    
                    #TODO: handle invalid response
                    
                    # if buf size is 0, socket close
                    if len(buf) == 0:
                        return 'RCLOSED', None
                    else:
                        frames = self._parse_response_frames(
                            buf, msg_type, show_fuzz_ui,
                        )
                        return (
                            self._response_batch_result(frames),
                            buf,
                        )
                
            elif (self.trans_layer == 'udp'):
                events = self._poll_with_stop(poller, 100)
                if events is None:
                    return None, None
                if not events:
                    logger.debug('recv: poll timeout')
                    return 'TIMEOUT', None
                fd, event = events[0]
                
                if event & select.POLLIN:
                    buf = b''
                    datagrams = []
                    while True:
                        events = self._poll_with_stop(poller, 100)
                        if events is None:
                            return None, None
                        if not events:
                            break
                        chunk, _ = sock.recvfrom(2048)
                        if not chunk:
                            break
                        offset_start = len(buf)
                        buf += chunk
                        datagrams.append({
                            'index': len(datagrams),
                            'offset_start': offset_start,
                            'offset_end': len(buf),
                            'timestamp': time.time(),
                        })

                    if len(buf) == 0:
                        return 'RCLOSED', None
                    else:
                        frames = self._parse_response_frames(
                            buf,
                            msg_type,
                            show_fuzz_ui,
                            datagrams=datagrams,
                        )
                        return (
                            self._response_batch_result(frames),
                            buf,
                        )
                else:
                    logger.debug('recv: no data')
        except RuntimeComponentRepairError:
            raise
        except Exception:
            logger.exception('Executor: receive failed')
        finally:
            poller.unregister(sock)
    
        return None, None

    def _set_ui_operation(
        self,
        operation: str
    ) -> None:
        with self.analyzer.lock:
            self.analyzer.current_operation = operation

    def _update_parser(
        self,
        response: bytes,
        show_fuzz_ui: bool
    ) -> None:
        if show_fuzz_ui:
            self._set_ui_operation('Updating parser with LLM')
        try:
            new_parser = self.mapper.update_parser(response)
            self.load_parser(new_parser)
        finally:
            if show_fuzz_ui:
                self._set_ui_operation('')
    
    def handle_crash(
        self,
        cons: Conversation,
        proc: subprocess.Popen | RemoteSUTProcess | None,
        msg_type: str,
        msg: bytes,
        stdout: str = '',
        stderr: str = '',
        request_recorded: bool = True,
    ):
        if msg_type in self.crash_testcases.keys() and msg in self.crash_testcases[msg_type]:
            pass
        else:
            self.crash_testcases.setdefault(msg_type, [])

            self.crash_testcases[msg_type].append(msg)
            if not request_recorded and msg_type != '-' and msg:
                cons.add_state(msg_type, 'CRASH')
                cons.add_data(msg, bytes())
            else:
                cons.add_state('-', 'CRASH')
                cons.add_data(bytes(), bytes())
            logger.debug(
                f'Program crash exitcode {getattr(proc, "returncode", None)}'
            )
            with self.analyzer.lock:
                self.analyzer.crash_num += 1

            if getattr(configs, 'fuzz_mode', '') != 'replay':
                if (
                    proc is not None
                    and hasattr(proc, 'communicate')
                    and stdout == ''
                    and stderr == ''
                ):
                    stdout, stderr = self._read_process_output(proc)
                self.save_cons(
                    cons,
                    stdout,
                    stderr,
                    True,
                    source='crash',
                    retention_reasons=('crash',),
                )
                self.generate_crash_report(
                    cons=cons,
                    proc=proc,
                    msg_type=msg_type,
                    msg=msg,
                    stdout=stdout,
                    stderr=stderr,
                )
    
    def _handle_crash_if_detected(
        self,
        cons: Conversation,
        proc: subprocess.Popen | RemoteSUTProcess | None,
        msg_type: str,
        msg: bytes,
        request_recorded: bool = True,
    ) -> bool:
        if self._is_remote_deployment():
            return self._handle_remote_crash_if_detected(
                cons,
                msg_type,
                msg,
                request_recorded=request_recorded,
            )
        if proc is None:
            return False
        return_code = proc.poll()
        if return_code is None:
            return False

        stdout = ''
        stderr = ''
        if return_code != 0:
            stdout, stderr = self._read_process_output(proc)

        if self._is_crash(return_code, stdout, stderr):
            self.handle_crash(
                cons,
                proc,
                msg_type,
                msg,
                stdout,
                stderr,
                request_recorded=request_recorded,
            )
            return True

        return False

    def _handle_remote_crash_if_detected(
        self,
        cons: Conversation,
        msg_type: str,
        msg: bytes,
        request_recorded: bool = True,
    ) -> bool:
        status = self._monitor().collect_failure_evidence()
        if status.state == UNREACHABLE:
            logger.debug(
                'Executor: UNKNOWN_REMOTE_STATUS; '
                f'detail={status.detail or "monitor unreachable"}'
            )
            return False
        stdout = status.stdout
        stderr = '\n'.join(
            part
            for part in (status.stderr, status.logs)
            if part
        )
        crashed = status.state == CRASHED
        if status.state == EXITED:
            return_code = status.returncode
            if return_code is None and (stdout or stderr):
                return_code = 1
            crashed = self._is_crash(return_code, stdout, stderr)
        if not crashed:
            if status.state == RUNNING:
                logger.debug('Executor: remote SUT still running')
            return False

        proc = RemoteSUTProcess(status)
        self.handle_crash(
            cons,
            proc,
            msg_type,
            msg,
            stdout,
            stderr,
            request_recorded=request_recorded,
        )
        return True
    
    def _is_crash(
        self,
        return_code: int | None,
        stdout: str = '',
        stderr: str = ''
    ) -> bool:
        if return_code is None:
            return False

        if return_code in CRASH_SIGNALS or return_code in CRASH_EXIT_CODES:
            return True

        if return_code == 0:
            return False

        output = f'{stdout}\n{stderr}'
        if any(marker in output for marker in ASAN_CRASH_MARKERS):
            return True

        return any(pattern.search(output) for pattern in RUNTIME_EXCEPTION_PATTERNS)
    
    def _read_process_output(
        self,
        proc: subprocess.Popen
    ) -> tuple[str, str]:
        try:
            stdout, stderr = proc.communicate(timeout=1)
        except subprocess.TimeoutExpired:
            return '', ''
        return self._decode_process_output(stdout), self._decode_process_output(stderr)
    
    def _decode_process_output(
        self,
        data
    ) -> str:
        if data is None:
            return ''
        if isinstance(data, bytes):
            return data.decode('utf-8', errors='backslashreplace')
        return str(data)

    def generate_crash_report(
        self,
        cons: Conversation,
        proc,
        msg_type: str,
        msg: bytes,
        stdout: str = '',
        stderr: str = '',
    ) -> None:
        """Ask the fuzz LLM to summarize a crash-inducing exchange."""
        try:
            chater = self._crash_report_chater()
            if chater is None:
                logger.debug('Executor: skip crash report; no LLM client')
                return

            target_folder = configs.results_path / 'crash_reports'
            target_folder.mkdir(parents=True, exist_ok=True)
            report_id = self._next_artifact_id(target_folder, 'report_', '.json')
            record = self._build_crash_record(
                report_id=report_id,
                cons=cons,
                proc=proc,
                msg_type=msg_type,
                msg=msg,
                stdout=stdout,
                stderr=stderr,
            )
            prompt = self._build_crash_report_prompt(record)
            report = asyncio.run(
                chater.chat_llm(
                    prompt=prompt,
                    usage='crash_report',
                )
            )
            record['llm_report'] = report or ''

            json_path = target_folder / f'report_{report_id}.json'
            md_path = target_folder / f'report_{report_id}.md'
            with json_path.open('w', encoding='utf-8') as f:
                json.dump(record, f, indent=2, ensure_ascii=False)
                f.write('\n')
            with md_path.open('w', encoding='utf-8') as f:
                f.write(report or 'The model returned no crash report.')
                f.write('\n')
            logger.debug(f'Executor: saved crash report {json_path}')
        except Exception:
            logger.exception('Executor: crash report generation failed')

    def _crash_report_chater(
        self
    ):
        mapper = getattr(self, 'mapper', None)
        producer = getattr(mapper, 'producer', None)
        return getattr(producer, 'chater', None)

    def _build_crash_record(
        self,
        report_id: str,
        cons: Conversation,
        proc,
        msg_type: str,
        msg: bytes,
        stdout: str,
        stderr: str,
    ) -> dict:
        return {
            'report_id': report_id,
            'target': getattr(configs, 'target_name', ''),
            'protocol': getattr(configs, 'pro_name', ''),
            'sut_deployment': getattr(configs, 'sut_deployment', 'local'),
            'crash': {
                'returncode': getattr(proc, 'returncode', None),
                'trigger_request_type': msg_type,
                'trigger_request': self._encode_bytes(msg),
                'stdout': stdout,
                'stderr': stderr,
            },
            'response_feedback': {
                'request_sequence': list(cons.req_seq),
                'response_sequence': list(cons.res_seq),
            },
            'exchanges': [
                {
                    'index': index,
                    'request_type': (
                        cons.req_seq[index]
                        if index < len(cons.req_seq)
                        else ''
                    ),
                    'response_type': (
                        cons.res_seq[index]
                        if index < len(cons.res_seq)
                        else ''
                    ),
                    'request': self._encode_bytes(request),
                    'response': self._encode_bytes(response),
                }
                for index, (request, response) in enumerate(cons.content)
            ],
        }

    def _build_crash_report_prompt(
        self,
        record: dict
    ) -> str:
        def compact_value(value):
            if isinstance(value, list):
                return [compact_value(item) for item in value]
            if not isinstance(value, dict):
                return value
            if value.get('encoding') == 'base64' and 'data' in value:
                return {
                    key: value[key]
                    for key in ('encoding', 'length', 'truncated', 'data')
                    if key in value
                }
            return {key: compact_value(item) for key, item in value.items()}

        compact = json.dumps(
            compact_value(record),
            ensure_ascii=False,
            separators=(',', ':'),
        )
        return (
            'TASK\nDraft a concise protocol-fuzzing crash report.\n\n'
            f'INPUT\nCRASH_EVIDENCE_JSON: {compact}\n\n'
            'CONTRACT\nUse only captured exchanges, response feedback, exit '
            'status, stdout, and stderr. Include Summary, Affected Target and '
            'Protocol, Crash/Sanitizer Evidence, Trigger and Preceding Context, '
            'Reproduction, Security Impact Hypothesis, and Triage Confidence. '
            'State insufficient evidence explicitly; do not invent root causes.\n\n'
            'OUTPUT\nMarkdown report only.'
        )

    def _encode_bytes(
        self,
        data: bytes | None
    ) -> dict:
        raw = data or bytes()
        sample = raw[:4096]
        return {
            'encoding': 'base64',
            'length': len(raw),
            'truncated': len(sample) < len(raw),
            'data': base64.b64encode(sample).decode('ascii'),
            'text': sample.decode('utf-8', errors='backslashreplace'),
            'hex': sample.hex(' '),
        }

    def _next_artifact_id(
        self,
        folder: Path,
        prefix: str,
        suffix: str,
    ) -> str:
        max_id = -1
        for item in folder.iterdir():
            if not item.is_file():
                continue
            name = item.name
            if not name.startswith(prefix) or not name.endswith(suffix):
                continue
            raw_id = name[len(prefix):-len(suffix)]
            if raw_id.isdigit():
                max_id = max(max_id, int(raw_id))
        return f'{max_id + 1:06d}'
        
    
    def load_parser(
        self,
        p: Parser
    ):
        name_space = {}
        try:
            with open(self.mapper.p_path(p), 'r', encoding='utf-8') as f:
                code = f.read()
                exec(code, name_space)
                obj = name_space[f'packet_parser']
                if not callable(obj):
                    raise TypeError('packet_parser is not callable')
                self.parser_func = obj
                self._parser_code = code
                self._parser_version = p.name
        except Exception as e:
            logger.debug(f'Mapper: generated failure {e}')
            raise RuntimeComponentRepairError(
                f'parser load failed [{getattr(p, "name", "unknown")}]: {e}'
            ) from e

    def load_checkers(
        self,
        checkers: dict[str, Checker]
    ) -> None:
        """Load the latest generated checker for each response type."""
        self.checker_funcs = {}
        self.checker_sources = {}
        for msg_type, checker in checkers.items():
            try:
                with open(self.mapper.c_path(checker), 'r', encoding='utf-8') as f:
                    code = f.read()
                tree = ast.parse(code)
                if not any(
                    isinstance(node, ast.FunctionDef)
                    and node.name == 'packet_checker'
                    for node in tree.body
                ):
                    raise TypeError('packet_checker is missing or not callable')
                self.checker_sources[msg_type] = code
            except Exception as e:
                logger.debug(
                    f'Executor: checker load failure [{msg_type}] {e}'
                )

    def load_observers(
        self,
        observers: dict[str, ResponseObserver]
    ) -> None:
        """Load the latest generated semantic observer for each response type."""
        self.observer_funcs = {}
        self.observer_sources = {}
        for msg_type, observer in observers.items():
            try:
                with open(self.mapper.o_path(observer), 'r', encoding='utf-8') as f:
                    code = f.read()
                tree = ast.parse(code)
                function_names = {
                    node.name
                    for node in tree.body
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                }
                function_name = next(
                    (
                        name for name in ('packet_observer', 'packet_hasher')
                        if name in function_names
                    ),
                    None,
                )
                if function_name is None:
                    raise TypeError('packet_observer is missing or not callable')
                self.observer_sources[msg_type] = (code, function_name)
            except Exception:
                logger.exception(
                    f'Executor: observer load failure [{msg_type}]'
                )

    def observe_response(
        self,
        response_type: str,
        response: bytes
    ) -> str:
        """Return the selected semantic digest for compatibility callers."""
        return self.observe_response_result(
            response_type,
            response,
        ).semantic_fingerprint

    @staticmethod
    def _response_component_candidates(response_type: str) -> list[str]:
        candidates = [response_type]
        family_match = re.search(
            r'(?<!\d)([1-5])\d{2}(?!\d)',
            response_type,
        )
        if family_match is not None:
            candidates.append(f'{family_match.group(1)}xx')
        candidates.append('__all__')
        return list(dict.fromkeys(candidates))

    @staticmethod
    def _component_scope(
        response_type: str,
        component_type: str | None,
    ) -> str:
        if component_type is None:
            return 'raw'
        if component_type == response_type:
            return 'exact'
        if component_type == '__all__':
            return 'generic'
        return 'family'

    def _request_and_refresh_response_components(
        self,
        response_type: str,
    ) -> None:
        producer = getattr(getattr(self, 'mapper', None), 'producer', None)
        if producer is None:
            return
        request = getattr(producer, 'request_response_components', None)
        if not callable(request):
            return
        request(response_type)

        # A previous background request may have completed since the last
        # response.  Reload only when metadata now contains an unloaded key.
        equip_checkers = getattr(self.mapper, 'equip_checkers', None)
        if callable(equip_checkers):
            equipped = equip_checkers()
            loaded_checkers = set(getattr(self, 'checker_sources', {})) | set(
                getattr(self, 'checker_funcs', {})
            )
            if set(equipped) != loaded_checkers:
                self.load_checkers(equipped)
        equip_observers = getattr(self.mapper, 'equip_observers', None)
        if (
            getattr(configs, 'observer_enabled', True)
            and callable(equip_observers)
        ):
            equipped = equip_observers()
            loaded = set(getattr(self, 'observer_sources', {})) | set(
                getattr(self, 'observer_funcs', {})
            )
            newly_available = set(equipped) - loaded
            if set(equipped) != loaded:
                self.load_observers(equipped)
                if response_type in newly_available and hasattr(
                    self,
                    'checked_request_response_pairs',
                ):
                    # Preserve raw fingerprints in persisted evidence while
                    # rebuilding in-memory semantic indexes for the newly
                    # available exact observer.
                    self._rebuild_observation_indexes(response_type)
                    self._reobserve_persisted_invalid_responses(response_type)
                    logger.debug(format_event(
                        'observer.promoted',
                        response_type=response_type,
                        from_scope='provisional',
                        to_scope='exact',
                    ))

    def _schedule_component_runtime_repair(
        self,
        component: str,
        component_type: str,
        source_code: str,
        error: str,
        runtime_input: bytes,
    ) -> None:
        """Repair optional response components without blocking fuzzing."""
        producer = getattr(getattr(self, 'mapper', None), 'producer', None)
        if not callable(getattr(producer, 'repair_runtime_component', None)):
            return
        if not hasattr(self, '_component_repair_lock'):
            self._component_repair_lock = threading.Lock()
            self._component_repair_pending = set()
        source_sha = hashlib.sha256(source_code.encode('utf-8')).hexdigest()
        key = (component, component_type, source_sha)
        with self._component_repair_lock:
            if key in self._component_repair_pending:
                return
            self._component_repair_pending.add(key)

        def repair_in_background() -> None:
            try:
                if component == 'checker':
                    equipped = self.mapper.equip_checkers()
                else:
                    equipped = self.mapper.equip_observers()
                metadata = equipped.get(component_type)
                version = getattr(metadata, 'name', 'unknown')
                result = self.mapper.repair_runtime_component(
                    component=component,
                    component_type=component_type,
                    version=version,
                    source_code=source_code,
                    error=error,
                    runtime_input=runtime_input,
                )
                if result is None:
                    return
                if component == 'checker':
                    self.mapper.checkers = self.mapper.producer.checkers
                    self.load_checkers(self.mapper.equip_checkers())
                else:
                    self.mapper.observers = self.mapper.producer.observers
                    self.load_observers(self.mapper.equip_observers())
            except Exception:
                logger.exception(
                    'Executor: background %s repair failed [%s]',
                    component,
                    component_type,
                )
            finally:
                with self._component_repair_lock:
                    self._component_repair_pending.discard(key)

        threading.Thread(
            target=repair_in_background,
            name=f'voltron-repair-{component}-{component_type}',
            daemon=True,
        ).start()

    def _response_component_is_quarantined(
        self,
        component: str,
        component_type: str,
    ) -> bool:
        equip_name = (
            'equip_checkers' if component == 'checker' else 'equip_observers'
        )
        equip = getattr(self.mapper, equip_name, None)
        check = getattr(self.mapper, '_component_quarantined', None)
        if not callable(equip) or not callable(check):
            return False
        try:
            metadata = equip().get(component_type)
        except (AttributeError, TypeError):
            return False
        return metadata is not None and check(
            component,
            component_type,
            getattr(metadata, 'name', 'unknown'),
        )

    def observe_response_result(
        self,
        response_type: str,
        response: bytes,
    ) -> ObservationResult:
        """Observe with exact/family/generic selection and explicit fallback."""
        fallback = hashlib.sha256(response).hexdigest()
        self._request_and_refresh_response_components(response_type)
        if not getattr(configs, 'observer_enabled', True):
            return ObservationResult(
                semantic_fingerprint=fallback,
                raw_fingerprint=fallback,
                scope='raw',
                component_type=None,
                provisional=False,
                error='observer disabled',
            )
        observer_sources = getattr(self, 'observer_sources', {})
        observer_funcs = getattr(self, 'observer_funcs', {})
        component_type = next(
            (
                candidate
                for candidate in self._response_component_candidates(
                    response_type
                )
                if candidate in observer_sources or candidate in observer_funcs
            ),
            None,
        )
        scope = self._component_scope(response_type, component_type)
        source = observer_sources.get(component_type) if component_type else None
        if source is not None and component_type is not None:
            if self._response_component_is_quarantined(
                'observer', component_type
            ):
                return ObservationResult(
                    semantic_fingerprint=fallback,
                    raw_fingerprint=fallback,
                    scope='raw',
                    component_type=component_type,
                    provisional=True,
                    error='observer version is quarantined',
                )
            code, function_name = source
            execution = self.mapper._run_dynamic_code_result(
                code,
                function_name,
                args=(response,),
            )
            digest = execution.value if execution.status == 'ok' else None
            if self._valid_observer_digest(digest):
                return ObservationResult(
                    semantic_fingerprint=digest,
                    raw_fingerprint=fallback,
                    scope=scope,
                    component_type=component_type,
                    provisional=scope != 'exact',
                )
            logger.warning(
                'Executor: observer failed or returned invalid digest [%s]',
                response_type,
            )
            error = execution.error or (
                'invalid_return: packet_observer must return lowercase SHA-256'
            )
            self._schedule_component_runtime_repair(
                'observer', component_type, code, error, response
            )
            return ObservationResult(
                semantic_fingerprint=fallback,
                raw_fingerprint=fallback,
                scope='raw',
                component_type=component_type,
                provisional=True,
                error=error,
            )

        observer = observer_funcs.get(component_type) if component_type else None
        if observer is None:
            return ObservationResult(
                semantic_fingerprint=fallback,
                raw_fingerprint=fallback,
                scope='raw',
                component_type=None,
                provisional=True,
                error='no observer available',
            )
        try:
            digest = observer(response)
            if not self._valid_observer_digest(digest):
                raise TypeError(
                    'packet_observer must return lowercase SHA-256'
                )
            return ObservationResult(
                semantic_fingerprint=digest,
                raw_fingerprint=fallback,
                scope=scope,
                component_type=component_type,
                provisional=scope != 'exact',
            )
        except Exception as error:
            logger.exception(
                f'Executor: observer failure [{response_type}]'
            )
            return ObservationResult(
                semantic_fingerprint=fallback,
                raw_fingerprint=fallback,
                scope='raw',
                component_type=component_type,
                provisional=True,
                error=f'{type(error).__name__}: {error}',
            )

    @staticmethod
    def _valid_observer_digest(digest: object) -> bool:
        return (
            isinstance(digest, str)
            and len(digest) == 64
            and digest == digest.lower()
            and all(char in '0123456789abcdef' for char in digest)
        )

    def observe_response_with_evolution(
        self,
        response_type: str,
        response: bytes
    ) -> str:
        """Evolve an observer only for semantically equivalent divergence."""
        if not getattr(configs, 'observer_enabled', True):
            return hashlib.sha256(response).hexdigest()
        if not hasattr(self, 'checked_response_samples'):
            self.checked_response_samples = {}
        if not hasattr(self, 'reviewed_response_samples'):
            self.reviewed_response_samples = {}
        if not hasattr(self, 'observer_evolution_failures'):
            self.observer_evolution_failures = set()
        if not hasattr(self, 'observer_semantic_reviews'):
            self.observer_semantic_reviews = {}
        digest = self.observe_response(response_type, response)
        if (
            response_type not in self.observer_funcs
            and response_type not in getattr(self, 'observer_sources', {})
        ):
            return digest

        previous_samples = self._historical_response_samples(response_type)
        samples_by_digest: dict[str, list[bytes]] = {}
        for sample in previous_samples:
            sample_digest = self.observe_response(response_type, sample)
            samples_by_digest.setdefault(sample_digest, []).append(sample)
        previous_digests = set(samples_by_digest)
        if not previous_samples or digest in previous_digests:
            return digest

        response_raw_hash = hashlib.sha256(response).hexdigest()
        equivalent_samples: list[bytes] = []
        try:
            for old_digest, old_samples in samples_by_digest.items():
                if old_digest == digest:
                    continue
                representative = old_samples[0]
                old_raw_hash = hashlib.sha256(representative).hexdigest()
                review_key = (
                    response_type,
                    old_raw_hash,
                    response_raw_hash,
                )
                reverse_key = (
                    response_type,
                    response_raw_hash,
                    old_raw_hash,
                )
                equivalent = self.observer_semantic_reviews.get(review_key)
                if equivalent is None:
                    equivalent = self.observer_semantic_reviews.get(reverse_key)
                if equivalent is None:
                    self._set_ui_operation(
                        'Comparing response semantics with LLM'
                    )
                    equivalent = (
                        self.mapper.producer
                        .responses_semantically_equivalent(
                            response_type=response_type,
                            old_response=representative,
                            new_response=response,
                        )
                    )
                    self.observer_semantic_reviews[review_key] = equivalent
                if equivalent:
                    equivalent_samples.extend(old_samples)
        except Exception:
            logger.exception(
                f'Executor: response semantic comparison failed '
                f'[{response_type}]'
            )
            return digest
        finally:
            self._set_ui_operation('')

        if not equivalent_samples:
            logger.debug(
                f'Executor: preserve distinct semantic observations '
                f'[{response_type}]'
            )
            return digest

        samples = list(dict.fromkeys([*equivalent_samples, response]))
        failure_key = tuple(sorted(
            hashlib.sha256(sample).hexdigest()
            for sample in samples
        ))
        if failure_key in self.observer_evolution_failures:
            return digest

        try:
            self._set_ui_operation('Updating response observer with LLM')
            evolved = self.mapper.producer.evolve_observer(
                response_type=response_type,
                samples=samples,
            )
            if evolved is None:
                self.observer_evolution_failures.add(failure_key)
                return digest
            self.mapper.observers = self.mapper.producer.observers
            self.load_observers(self.mapper.equip_observers())
            self._rebuild_observation_indexes(response_type)
            self._reobserve_persisted_invalid_responses(response_type)
            return self.observe_response(response_type, response)
        except Exception:
            self.observer_evolution_failures.add(failure_key)
            logger.exception(
                f'Executor: observer evolution failed [{response_type}]'
            )
            return digest
        finally:
            self._set_ui_operation('')

    def check_response(
        self,
        response_type: str,
        response: bytes
    ) -> bool:
        """Compatibility boolean: only a confirmed rejection is False."""
        evaluation = self.evaluate_response(response_type, response)
        self.last_checker_evaluation = evaluation
        return evaluation.status != 'non_compliant'

    def evaluate_response(
        self,
        response_type: str,
        response: bytes,
    ) -> CheckerEvaluation:
        """Return a four-state checker result with component provenance."""
        self._request_and_refresh_response_components(response_type)
        checker_funcs = getattr(self, 'checker_funcs', {})
        checker_sources = getattr(self, 'checker_sources', {})
        component_type = next(
            (
                candidate
                for candidate in self._response_component_candidates(
                    response_type
                )
                if candidate in checker_funcs or candidate in checker_sources
            ),
            None,
        )
        checker = checker_funcs.get(component_type) if component_type else None
        checker_source = (
            checker_sources.get(component_type) if component_type else None
        )
        if checker is None and checker_source is None:
            logger.debug(
                f'Executor: no checker for response type {response_type}'
            )
            return CheckerEvaluation(
                status='unchecked',
                scope='none',
                component_type=None,
                error='no checker available',
            )

        if (
            checker_source is not None
            and component_type is not None
            and self._response_component_is_quarantined(
                'checker', component_type
            )
        ):
            return CheckerEvaluation(
                status='unchecked',
                scope=self._component_scope(response_type, component_type),
                component_type=component_type,
                error='checker version is quarantined',
            )

        try:
            if checker_source is not None:
                execution = self.mapper._run_dynamic_code_result(
                    checker_source,
                    'packet_checker',
                    args=(response,),
                )
                is_valid = (
                    execution.value if execution.status == 'ok' else None
                )
                if execution.status != 'ok':
                    raise RuntimeError(
                        execution.error
                        or 'checker execution failed or timed out'
                    )
            else:
                is_valid = checker(response)
            if not isinstance(is_valid, bool):
                raise TypeError('packet_checker must return bool')
        except Exception as e:
            logger.debug(
                f'Executor: checker failure [{response_type}] {e}'
            )
            if checker_source is not None and component_type is not None:
                self._schedule_component_runtime_repair(
                    'checker',
                    component_type,
                    checker_source,
                    f'{type(e).__name__}: {e}',
                    response,
                )
            return CheckerEvaluation(
                status='unchecked',
                scope=self._component_scope(response_type, component_type),
                component_type=component_type,
                error=f'{type(e).__name__}: {e}',
            )

        if is_valid:
            scope = self._component_scope(response_type, component_type)
            return CheckerEvaluation(
                status='compliant' if scope == 'exact' else 'uncertain',
                scope=scope,
                component_type=component_type,
            )

        logger.debug(format_event(
            'checker.reject',
            response_type=response_type,
            length=len(response),
            response=response,
        ))
        return CheckerEvaluation(
            status='non_compliant',
            scope=self._component_scope(response_type, component_type),
            component_type=component_type,
        )

    def check_response_during_fuzzing(
        self,
        request_type: str,
        response_type: str,
        response: bytes,
        enabled: bool
    ) -> bool:
        """Deduplicate exchanges before running fuzzing-stage checkers."""
        if not enabled:
            return True

        # Response-code deduplication happens before any observer/checker work
        # so repeated responses do not consume component or compliance budget.
        dedup_key = response_type
        with self._invalid_response_lock:
            if dedup_key in self.checked_request_response_pairs:
                logger.debug(format_event(
                    'checker.deduplicated',
                    request_type=request_type,
                    response_type=response_type,
                    deduplication='response_code',
                ))
                return True
            self.checked_request_response_pairs.add(dedup_key)

        response_observation = self.observe_response_with_evolution(
            response_type,
            response,
        )
        observation = self.observe_response_result(response_type, response)
        response_observation = observation.semantic_fingerprint
        raw_digest = hashlib.sha256(response).hexdigest()
        with self._invalid_response_lock:
            self.checked_response_samples[
                (request_type, response_type, raw_digest)
            ] = response

        is_valid = self.check_response(response_type, response)
        evaluation = getattr(self, 'last_checker_evaluation', None)
        if not isinstance(evaluation, CheckerEvaluation):
            evaluation = CheckerEvaluation(
                status='compliant' if is_valid else 'non_compliant',
                scope='exact',
                component_type=response_type,
            )
        if not hasattr(self, 'component_evidence'):
            self.component_evidence = {}
        self.component_evidence[
            (request_type, response_type, raw_digest)
        ] = {
            'checker': asdict(evaluation),
            'observer': asdict(observation),
        }
        self._record_response_component_usage(
            request_type,
            response_type,
            evaluation,
            observation,
        )
        logger.debug(format_event(
            'response.components',
            request_type=request_type,
            response_type=response_type,
            checker_status=evaluation.status,
            checker_scope=evaluation.scope,
            checker_component=evaluation.component_type or '',
            observer_scope=observation.scope,
            observer_component=observation.component_type or '',
            observer_provisional=observation.provisional,
            raw_fingerprint=observation.raw_fingerprint,
            semantic_fingerprint=observation.semantic_fingerprint,
        ))
        return is_valid

    def _record_response_component_usage(
        self,
        request_type: str,
        response_type: str,
        evaluation: CheckerEvaluation,
        observation: ObservationResult,
    ) -> None:
        """Persist auditable component decisions and an incremental summary."""
        results_path = getattr(configs, 'results_path', None)
        if not isinstance(results_path, Path) or not results_path.is_dir():
            return
        if not hasattr(self, '_component_usage_lock'):
            self._component_usage_lock = threading.Lock()
        with self._component_usage_lock:
            record = {
                'timestamp': time.time(),
                'request_type': request_type,
                'response_type': response_type,
                'checker': asdict(evaluation),
                'observer': asdict(observation),
            }
            try:
                usage_path = diagnostics_path(
                    results_path,
                    'events',
                    'response_component_usage.jsonl',
                )
                usage_path.parent.mkdir(parents=True, exist_ok=True)
                with usage_path.open('a', encoding='utf-8') as stream:
                    json.dump(record, stream, ensure_ascii=False)
                    stream.write('\n')

                if not hasattr(self, '_component_usage_counts'):
                    self._component_usage_counts = {
                        'checker_status': {},
                        'checker_scope': {},
                        'observer_scope': {},
                    }
                    self._component_observed_types = set()
                    self._component_provisional_count = 0
                dimensions = (
                    ('checker_status', evaluation.status),
                    ('checker_scope', evaluation.scope),
                    ('observer_scope', observation.scope),
                )
                for dimension, value in dimensions:
                    counts = self._component_usage_counts[dimension]
                    counts[value] = counts.get(value, 0) + 1
                self._component_observed_types.add(response_type)
                if observation.provisional:
                    self._component_provisional_count += 1

                summary = {
                    'observed_response_types': sorted(
                        self._component_observed_types
                    ),
                    'observed_response_type_count': len(
                        self._component_observed_types
                    ),
                    **self._component_usage_counts,
                    'observer_provisional_count': (
                        self._component_provisional_count
                    ),
                }
                summary_path = diagnostics_path(
                    results_path,
                    'summary',
                    'response_component_summary.json',
                )
                summary_path.parent.mkdir(parents=True, exist_ok=True)
                temporary_path = summary_path.with_suffix('.json.tmp')
                with temporary_path.open('w', encoding='utf-8') as stream:
                    json.dump(summary, stream, indent=2, ensure_ascii=False)
                    stream.write('\n')
                temporary_path.replace(summary_path)
            except Exception:
                logger.exception(
                    'Executor: failed to persist response component usage'
                )

    def handle_nonconforming_response(
        self,
        cons: Conversation,
        response_type: str
    ) -> None:
        """Review one unique checker rejection and act on the LLM verdict."""
        if not getattr(configs, 'compliance_analysis', True):
            logger.debug(
                'Executor: compliance analysis disabled; checker rejection '
                f'not reviewed [{response_type}]'
            )
            return
        if not cons.content or not cons.req_seq:
            logger.debug(
                'Executor: cannot review response without conversation data'
            )
            return

        request, response = cons.content[-1]
        request_type = cons.req_seq[-1]
        if not response:
            return

        dedup_key = response_type
        with self._invalid_response_lock:
            if dedup_key in self.reviewed_invalid_responses:
                logger.debug(
                    'Executor: duplicate non-conforming response skipped '
                    f'[{request_type}/{response_type}] by response code'
                )
                return
            self.reviewed_invalid_responses.add(dedup_key)
            self.reviewed_response_samples[
                (
                    request_type,
                    response_type,
                    hashlib.sha256(response).hexdigest(),
                )
            ] = response

        try:
            self._set_ui_operation(
                'Checking possible non-compliance with LLM'
            )
            analysis = self.mapper.producer.review_nonconforming_response(
                request_type=request_type,
                response_type=response_type,
                request=request,
                response=response,
            )
        except Exception:
            logger.exception(
                'Executor: non-conforming response review failed '
                f'[{request_type}/{response_type}]'
            )
            return
        finally:
            self._set_ui_operation('')

        verdict = analysis.get('verdict', 'uncertain')
        if verdict == 'non_compliant':
            saved = self.save_invalid_response(
                cons,
                response_type,
                analysis=analysis,
            )
            if saved:
                with self.analyzer.lock:
                    self.analyzer.non_compliant_num += 1
            return

        if verdict == 'compliant':
            try:
                self._set_ui_operation('Updating checker with LLM')
                checker = self.mapper.producer.evolve_checker(
                    response_type=response_type,
                    response=response,
                    analysis=analysis,
                )
                if checker is not None:
                    self.load_checkers(self.mapper.equip_checkers())
                    logger.debug(
                        'Executor: checker hot-reloaded after false positive '
                        f'[{request_type}/{response_type}]'
                    )
                else:
                    logger.debug(
                        'Executor: checker evolution produced no update '
                        f'[{request_type}/{response_type}]'
                    )
            except Exception:
                logger.exception(
                    'Executor: checker evolution failed '
                    f'[{request_type}/{response_type}]'
                )
            finally:
                self._set_ui_operation('')
            return

        logger.debug(
            'Executor: compliance review uncertain; no response recorded and '
            f'no checker modified [{request_type}/{response_type}]'
        )

    def save_invalid_response(
        self,
        cons: Conversation,
        response_type: str,
        analysis: dict | None = None
    ) -> bool:
        """Persist one unique, confirmed non-compliant response."""
        if not cons.content or not cons.req_seq:
            return False

        target_folder = configs.results_path / 'invalid_responses'
        target_folder.mkdir(parents=True, exist_ok=True)
        request, response = cons.content[-1]
        request_type = cons.req_seq[-1]
        response_digest = hashlib.sha256(response).hexdigest()
        response_observation = self.observe_response(response_type, response)
        dedup_key = (request_type, response_type, response_observation)
        marker_digest = hashlib.sha256(
            json.dumps(dedup_key, separators=(',', ':')).encode('utf-8')
        ).hexdigest()
        marker_path = target_folder / f'.dedup_{marker_digest}'

        with self._invalid_response_lock:
            if self._invalid_response_exists(target_folder, dedup_key):
                logger.debug(format_event(
                    'invalid_response.deduplicated',
                    request_type=request_type,
                    response_type=response_type,
                    response_observation=response_observation,
                ))
                return False

            try:
                marker_fd = os.open(
                    marker_path,
                    os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                    0o600,
                )
                os.close(marker_fd)
            except FileExistsError:
                logger.debug(format_event(
                    'invalid_response.deduplicated',
                    request_type=request_type,
                    response_type=response_type,
                    response_observation=response_observation,
                ))
                return False

            file_count = sum(
                1
                for path in target_folder.iterdir()
                if path.is_file() and path.suffix == '.pkl'
            )
            file_id = f'{file_count:06d}'

            try:
                with open(
                    target_folder / f'cons_{file_id}.pkl',
                    'wb'
                ) as f:
                    pickle.dump(cons, f)

                with open(
                    target_folder / f'cons_{file_id}.raw',
                    'wb'
                ) as f:
                    for saved_request, saved_response in cons.content:
                        f.write(
                            b'REQUEST '
                            + str(len(saved_request)).encode()
                            + b'\n'
                        )
                        f.write(saved_request + b'\n')
                        f.write(
                            b'RESPONSE '
                            + str(len(saved_response)).encode()
                            + b'\n'
                        )
                        f.write(saved_response + b'\n')

                with open(
                    target_folder / f'cons_{file_id}.info',
                    'w',
                    encoding='utf-8'
                ) as f:
                    f.write(f'response_type: {response_type}\n')
                    f.write(f'request_types: {cons.req_seq}\n')
                    f.write(f'response_types: {cons.res_seq}\n')

                record = {
                    'request_type': request_type,
                    'response_type': response_type,
                    'response_sha256': response_digest,
                    'response_observation': response_observation,
                    'request': {
                        'encoding': 'base64',
                        'data': base64.b64encode(request).decode('ascii'),
                    },
                    'response': {
                        'encoding': 'base64',
                        'data': base64.b64encode(response).decode('ascii'),
                    },
                    'analysis': analysis or {},
                }
                with open(
                    target_folder / f'cons_{file_id}.analysis.json',
                    'w',
                    encoding='utf-8'
                ) as f:
                    json.dump(record, f, indent=2, ensure_ascii=False)
            except Exception:
                marker_path.unlink(missing_ok=True)
                logger.exception(
                    'Executor: failed to save non-compliant response'
                )
                return False

        logger.debug(format_event(
            'invalid_response.saved',
            testcase=f'cons_{file_id}',
            request_type=request_type,
            response_type=response_type,
            response_sha256=response_digest,
            response_observation=response_observation,
        ))
        return True

    def _invalid_response_exists(
        self,
        target_folder: Path,
        dedup_key: tuple[str, str, str]
    ) -> bool:
        """Check persisted analysis files, including files from older runs."""
        request_type, response_type, response_observation = dedup_key
        for path in target_folder.glob('cons_*.analysis.json'):
            try:
                with path.open('r', encoding='utf-8') as f:
                    record = json.load(f)
                saved_hash = (
                    record.get('response_observation')
                    or record.get('response_hash')
                )
                if not saved_hash:
                    encoded = record.get('response', {}).get('data')
                    if not isinstance(encoded, str):
                        continue
                    saved_response = base64.b64decode(
                        encoded,
                        validate=True,
                    )
                    saved_hash = self.observe_response(
                        response_type,
                        saved_response,
                    )
                if (
                    record.get('request_type') == request_type
                    and record.get('response_type') == response_type
                    and saved_hash == response_observation
                ):
                    return True
            except Exception:
                logger.exception(
                    f'Executor: invalid response index read failed {path}'
                )
        return False

    def _historical_response_samples(
        self,
        response_type: str
    ) -> list[bytes]:
        samples = [
            response
            for (_, saved_type, _), response
            in self.checked_response_samples.items()
            if saved_type == response_type
        ]
        target_folder = configs.results_path / 'invalid_responses'
        if target_folder.is_dir():
            for path in target_folder.glob('cons_*.analysis.json'):
                try:
                    with path.open('r', encoding='utf-8') as f:
                        record = json.load(f)
                    if record.get('response_type') != response_type:
                        continue
                    encoded = record.get('response', {}).get('data')
                    if isinstance(encoded, str):
                        samples.append(base64.b64decode(
                            encoded,
                            validate=True,
                        ))
                except Exception:
                    logger.exception(
                        f'Executor: historical response read failed {path}'
                    )
        return list(dict.fromkeys(samples))

    def _rebuild_observation_indexes(
        self,
        response_type: str
    ) -> None:
        # Observation changes no longer alter response-code deduplication.
        # Preserve the fact that this code was already checked/reviewed if a
        # historical sample exists, while leaving other response codes intact.
        if any(
            saved_type == response_type
            for (_, saved_type, _), _response
            in self.checked_response_samples.items()
        ):
            self.checked_request_response_pairs.add(response_type)
        if any(
            saved_type == response_type
            for (_, saved_type, _), _response
            in self.reviewed_response_samples.items()
        ):
            self.reviewed_invalid_responses.add(response_type)

    def _reobserve_persisted_invalid_responses(
        self,
        response_type: str
    ) -> None:
        target_folder = configs.results_path / 'invalid_responses'
        if not target_folder.is_dir():
            return

        records = []
        for path in target_folder.glob('cons_*.analysis.json'):
            try:
                with path.open('r', encoding='utf-8') as f:
                    record = json.load(f)
                if record.get('response_type') == response_type:
                    encoded = record.get('response', {}).get('data')
                    if isinstance(encoded, str):
                        response = base64.b64decode(
                            encoded,
                            validate=True,
                        )
                        record['response_observation'] = self.observe_response(
                            response_type,
                            response,
                        )
                        temp_path = path.with_suffix(path.suffix + '.tmp')
                        with temp_path.open('w', encoding='utf-8') as f:
                            json.dump(
                                record,
                                f,
                                indent=2,
                                ensure_ascii=False,
                            )
                        temp_path.replace(path)
                records.append(record)
            except Exception:
                logger.exception(
                    f'Executor: persisted response reobserve failed {path}'
                )

        for marker in target_folder.glob('.dedup_*'):
            marker.unlink(missing_ok=True)
        for record in records:
            request_type = record.get('request_type')
            saved_type = record.get('response_type')
            saved_hash = (
                record.get('response_observation')
                or record.get('response_hash')
            )
            if (
                isinstance(saved_type, str)
                and not isinstance(saved_hash, str)
            ):
                encoded = record.get('response', {}).get('data')
                if isinstance(encoded, str):
                    try:
                        saved_hash = self.observe_response(
                            saved_type,
                            base64.b64decode(encoded, validate=True),
                        )
                    except Exception:
                        logger.exception(
                            'Executor: marker observation reconstruction failed'
                        )
            if not all(isinstance(value, str) for value in (
                request_type,
                saved_type,
                saved_hash,
            )):
                continue
            key = (request_type, saved_type, saved_hash)
            marker_digest = hashlib.sha256(
                json.dumps(key, separators=(',', ':')).encode('utf-8')
            ).hexdigest()
            (target_folder / f'.dedup_{marker_digest}').touch(exist_ok=True)
        
    def save_cons(
        self,
        cons: Conversation,
        stdout: str = '',
        stderr: str = '',
        crash: bool = False,
        *,
        source: str = '',
        retention_reasons: list[str] | tuple[str, ...] = (),
    ) -> bool:
        """Store a replayable conversation and its phase/iteration provenance."""
        seed_digest = self._seed_digest(cons, crash)
        seed_lock = getattr(self, '_saved_seed_lock', None)
        if seed_lock is None:
            seed_lock = threading.Lock()
            self._saved_seed_lock = seed_lock
        with seed_lock:
            saved_seed_digests = getattr(self, '_saved_seed_digests', None)
            if saved_seed_digests is None:
                saved_seed_digests = set()
                self._saved_seed_digests = saved_seed_digests
            if seed_digest in saved_seed_digests:
                logger.debug('Executor: skip duplicate replayable seed')
                return False
            saved_seed_digests.add(seed_digest)

        pending = ''
        if crash:
            pending = '_crash'
        target_folder = configs.results_path / 'raw_testcases'
        enrich_folder = configs.results_path / 'enrich_testcases'
        if not target_folder.is_dir():
            target_folder.mkdir()

        if not enrich_folder.is_dir():
            enrich_folder.mkdir()
            
        file_count = 0
        for item in target_folder.iterdir():
            if item.is_file():
                file_count += 1
        
        file_count = str(file_count)
        while len(file_count) < 6:
            file_count = '0' + file_count

        with open(target_folder / f'cons_{file_count}{pending}.raw', 'ab') as f:
            for request, response in cons.content:
                if request:
                    f.write(request + b'\n')
                    f.write(response + b'\n')
        
        with open(enrich_folder / f'request_{file_count}{pending}.raw', 'ab') as f:
            for request, _ in cons.content:
                if request:
                    f.write(request + b'\n')
        
        file_count = 0
        target_folder = configs.results_path / 'replayable_testcases'
        if not target_folder.is_dir():
            target_folder.mkdir()
        for item in target_folder.iterdir():
            if item.is_file():
                file_count += 1
                
        file_count = str(file_count)
        while len(file_count) < 6:
            file_count = '0' + file_count        
        with open(target_folder / f"cons_{file_count}{pending}.pkl", "wb") as f:
            pickle.dump(cons, f)

        self._record_replayable_seed_metadata(
            filename=f'cons_{file_count}{pending}.pkl',
            cons=cons,
            seed_digest=seed_digest,
            crash=crash,
            source=source,
            retention_reasons=retention_reasons,
        )
            
        
        logger.debug(f'run: save cons_{file_count}')    
        info_file = configs.results_path / 'cons_info'
        with open(info_file, 'a', encoding='utf-8') as f:
            f.write(file_count + '\n')
            f.write('-'.join(cons.res_seq) + '\n')
            f.write(f'stdout: {stdout}' + '\n')
            f.write(f'stderr: {stderr}' + '\n')
        return True

    def _record_replayable_seed_metadata(
        self,
        *,
        filename: str,
        cons: Conversation,
        seed_digest: str,
        crash: bool,
        source: str,
        retention_reasons: list[str] | tuple[str, ...],
    ) -> None:
        """Append byte-free provenance for one successfully saved replay seed."""
        with analyzer.lock:
            phase = analyzer.active_phase or analyzer._phase_from_stage() or 'unknown'
            snapshot_phase = getattr(analyzer, '_state_snapshot_phase', '')
            phase_iteration = (
                getattr(analyzer, '_state_snapshot_phase_iteration', None)
                if snapshot_phase == phase else None
            )
            components = list(getattr(analyzer, '_state_snapshot_components', ()))

        metadata = {
            'schema_version': 1,
            'sequence_file': f'replayable_testcases/{filename}',
            'saved_at': time.time(),
            'seed_sha256': seed_digest,
            'crash': bool(crash),
            'phase': phase,
            'phase_iteration': phase_iteration,
            'source': source or ('crash' if crash else 'unknown'),
            'retention_reasons': list(retention_reasons),
            'request_types': list(cons.req_seq),
            'response_types': list(cons.res_seq),
            'request_count': len(cons.req_seq),
            'response_count': len(cons.res_seq),
            'unique_response_types': len(set(cons.res_seq)),
            'unique_response_transitions': len(
                set(zip(cons.res_seq, cons.res_seq[1:]))
            ),
            'component_versions': components,
        }
        manifest = diagnostics_path(
            configs.results_path,
            'events',
            'replayable_seed_manifest.jsonl',
        )
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest_lock = getattr(self, '_replayable_seed_manifest_lock', None)
        if manifest_lock is None:
            manifest_lock = threading.Lock()
            self._replayable_seed_manifest_lock = manifest_lock
        with manifest_lock, manifest.open('a', encoding='utf-8') as stream:
            stream.write(json.dumps(metadata, ensure_ascii=False) + '\n')

    @staticmethod
    def _seed_digest(cons: Conversation, crash: bool) -> str:
        """Return a stable digest for a replayable conversation.

        Retention happens in both model learning and fuzzing.  Include the
        symbolic sequences and raw byte pairs so only an exact replay seed is
        deduplicated; crashes retain a separate corpus from normal traffic.
        """
        digest = hashlib.sha256()
        digest.update(b'crash=' + (b'1' if crash else b'0') + b'\0')
        for sequence in (cons.req_seq, cons.res_seq):
            digest.update(len(sequence).to_bytes(8, 'big'))
            for item in sequence:
                encoded = item.encode('utf-8', errors='surrogatepass')
                digest.update(len(encoded).to_bytes(8, 'big'))
                digest.update(encoded)
        digest.update(len(cons.content).to_bytes(8, 'big'))
        for request, response in cons.content:
            digest.update(len(request).to_bytes(8, 'big'))
            digest.update(request)
            digest.update(len(response).to_bytes(8, 'big'))
            digest.update(response)
        return digest.hexdigest()
