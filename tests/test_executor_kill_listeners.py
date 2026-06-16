import signal
import subprocess

from voltron.executor import executor as executor_module
from voltron.executor.executor import Executor


class RecordingLogger:
    def __init__(self) -> None:
        self.messages = []

    def debug(self, message) -> None:
        self.messages.append(str(message))


def make_executor() -> Executor:
    return Executor.__new__(Executor)


def test_parse_ss_matches_exact_port():
    executor = make_executor()
    output = (
        'tcp LISTEN 0 128 127.0.0.1:21 0.0.0.0:* '
        'users:(("ftp",pid=101,fd=3))\n'
        'tcp LISTEN 0 128 127.0.0.1:2121 0.0.0.0:* '
        'users:(("ftp",pid=202,fd=3))\n'
        'udp UNCONN 0 0 [::]:21 [::]:* '
        'users:(("ftp6",pid=303,fd=4))\n'
    )

    pids, found = executor._parse_listener_output(output, 21, 'ss')

    assert found is True
    assert pids == {101, 303}


def test_parse_netstat_does_not_skip_first_result():
    executor = make_executor()
    output = (
        'tcp 0 0 127.0.0.1:2200 0.0.0.0:* LISTEN 456/server\n'
    )

    pids, found = executor._parse_listener_output(
        output,
        2200,
        'netstat',
    )

    assert found is True
    assert pids == {456}


def test_find_listener_pids_falls_back_to_netstat(monkeypatch):
    executor = make_executor()
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command[0])
        if command[0] == 'ss':
            return subprocess.CompletedProcess(
                command,
                1,
                stdout='',
                stderr='Operation not permitted',
            )
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=(
                'tcp 0 0 127.0.0.1:2200 0.0.0.0:* '
                'LISTEN 789/server\n'
            ),
            stderr='',
        )

    monkeypatch.setattr(executor_module.subprocess, 'run', fake_run)

    pids, found = executor._find_listener_pids(2200)

    assert calls == ['ss', 'netstat']
    assert found is True
    assert pids == {789}


def test_kill_listeners_continues_after_permission_error(monkeypatch):
    executor = make_executor()
    logger = RecordingLogger()
    killed = []
    queries = iter([
        ({111, 222}, True),
        (set(), False),
    ])
    monkeypatch.setattr(executor_module, 'logger', logger)
    monkeypatch.setattr(
        executor,
        '_find_listener_pids',
        lambda port: next(queries),
    )
    monkeypatch.setattr(
        executor,
        '_wait_for_process_exit',
        lambda pid, timeout: True,
    )

    def fake_kill(pid, sig):
        assert sig == signal.SIGKILL
        killed.append(pid)
        if pid == 111:
            raise PermissionError('denied')

    monkeypatch.setattr(executor_module.os, 'kill', fake_kill)

    executor.kill_listeners(2200)

    assert killed == [111, 222]
    assert any('permission denied' in message for message in logger.messages)
    assert any('listener stopped' in message for message in logger.messages)


def test_logs_when_listener_pid_is_hidden(monkeypatch):
    executor = make_executor()
    logger = RecordingLogger()
    monkeypatch.setattr(executor_module, 'logger', logger)
    monkeypatch.setattr(
        executor,
        '_find_listener_pids',
        lambda port: (set(), True),
    )

    executor.kill_listeners(2200)

    assert any(
        'PID is unavailable' in message
        for message in logger.messages
    )


def test_logs_when_listener_is_automatically_restarted(monkeypatch):
    executor = make_executor()
    logger = RecordingLogger()
    queries = iter([
        ({111}, True),
        ({222}, True),
    ])
    monkeypatch.setattr(executor_module, 'logger', logger)
    monkeypatch.setattr(
        executor,
        '_find_listener_pids',
        lambda port: next(queries),
    )
    monkeypatch.setattr(
        executor,
        '_wait_for_process_exit',
        lambda pid, timeout: True,
    )
    monkeypatch.setattr(executor_module.os, 'kill', lambda pid, sig: None)

    executor.kill_listeners(2200)

    assert any(
        'port remains occupied' in message
        and 'pids=[222]' in message
        for message in logger.messages
    )
