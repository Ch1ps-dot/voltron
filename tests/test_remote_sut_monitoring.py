import socket
import threading
from types import SimpleNamespace

from voltron.executor import executor as executor_module
from voltron.executor.conversation import Conversation
from voltron.executor.executor import Executor
from voltron.executor.sut_monitor import (
    CRASHED,
    RUNNING,
    UNREACHABLE,
    SUTStatus,
)


class RecordingLogger:
    def __init__(self) -> None:
        self.messages = []

    def debug(self, message) -> None:
        self.messages.append(str(message))


class FakeMonitor:
    def __init__(self, status: SUTStatus) -> None:
        self._status = status
        self.started = False
        self.stopped = False

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.stopped = True

    def status(self) -> SUTStatus:
        return self._status

    def collect_failure_evidence(self) -> SUTStatus:
        return self._status


def make_remote_executor(status: SUTStatus) -> Executor:
    executor = Executor.__new__(Executor)
    executor.sut_deployment = 'remote'
    executor.sut_monitor = FakeMonitor(status)
    executor.crash_testcases = {}
    executor.analyzer = SimpleNamespace(
        lock=threading.RLock(),
        crash_num=0,
        path_num=0,
    )
    return executor


def test_setup_socket_uses_configured_tcp_host(monkeypatch):
    executor = Executor.__new__(Executor)
    executor.trans_layer = 'tcp'
    executor.host = '192.0.2.10'
    executor.port = 31337

    calls = []

    class FakeSocket:
        def setblocking(self, flag):
            calls.append(('setblocking', flag))

    def fake_create_connection(endpoint):
        calls.append(endpoint)
        return FakeSocket()

    monkeypatch.setattr(socket, 'create_connection', fake_create_connection)

    assert executor.setup_socket() is not None
    assert calls[0] == ('192.0.2.10', 31337)
    assert calls[1] == ('setblocking', False)


def test_remote_timeout_keeps_timeout_when_agent_reports_running():
    executor = make_remote_executor(SUTStatus(state=RUNNING))
    cons = Conversation()

    assert executor._handle_crash_if_detected(
        cons,
        None,
        'PING',
        b'PING',
        request_recorded=False,
    ) is False
    assert executor.analyzer.crash_num == 0
    assert cons.res_seq == []


def test_remote_timeout_becomes_crash_when_agent_reports_crash(monkeypatch):
    executor = make_remote_executor(
        SUTStatus(
            state=CRASHED,
            returncode=-11,
            stderr='ERROR: AddressSanitizer: heap-use-after-free',
        )
    )
    cons = Conversation()
    saved = []
    reports = []
    monkeypatch.setattr(executor, 'save_cons', lambda *args: saved.append(args))
    monkeypatch.setattr(
        executor,
        'generate_crash_report',
        lambda **kwargs: reports.append(kwargs),
    )
    monkeypatch.setattr(executor_module.configs, 'fuzz_mode', 'fuzz', raising=False)

    assert executor._handle_crash_if_detected(
        cons,
        None,
        'PING',
        b'PING',
        request_recorded=False,
    ) is True

    assert executor.analyzer.crash_num == 1
    assert cons.res_seq == ['CRASH']
    assert saved
    assert reports[0]['stderr'] == 'ERROR: AddressSanitizer: heap-use-after-free'


def test_remote_agent_unreachable_does_not_block_timeout(monkeypatch):
    executor = make_remote_executor(SUTStatus(state=UNREACHABLE))
    logger = RecordingLogger()
    monkeypatch.setattr(executor_module, 'logger', logger)
    cons = Conversation()

    assert executor._handle_crash_if_detected(
        cons,
        None,
        'PING',
        b'PING',
        request_recorded=False,
    ) is False

    assert any('UNKNOWN_REMOTE_STATUS' in message for message in logger.messages)
    assert cons.res_seq == []


def test_remote_interact_does_not_use_local_process_controls(monkeypatch):
    executor = make_remote_executor(SUTStatus(state=RUNNING, port_listening=True))
    executor.host = '198.51.100.10'
    executor.port = 9999
    executor.trans_layer = 'tcp'
    executor.setup_time_s = 0
    executor.stop_event = threading.Event()
    executor.parser_func = lambda data: b'OK'
    executor.check_response_during_fuzzing = lambda *args, **kwargs: True
    executor._handle_crash_if_detected = lambda *args, **kwargs: False
    executor.setup_socket = lambda: SimpleNamespace(
        close=lambda: None,
        fileno=lambda: -1,
    )
    executor.net_recv = lambda *args, **kwargs: ('TIMEOUT', None)
    executor.net_send = lambda *args, **kwargs: (False, None)
    executor._monitor().stop = lambda: None
    monkeypatch.setattr(executor, 'kill_listeners', lambda *_: (_ for _ in ()).throw(AssertionError()))
    monkeypatch.setattr(executor, 'run_exe', lambda: (_ for _ in ()).throw(AssertionError()))
    monkeypatch.setattr(executor, '_terminate_process_group', lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError()))

    result, cons = executor._interact_once([])

    assert result is True
    assert cons is not None
