import subprocess
from pathlib import Path
from types import SimpleNamespace

from voltron.executor import executor as executor_module
from voltron.executor.executor import Executor


class RecordingLogger:
    def __init__(self) -> None:
        self.messages = []

    def debug(self, message) -> None:
        self.messages.append(str(message))


def make_executor(tmp_path: Path) -> Executor:
    executor = Executor.__new__(Executor)
    executor.run_script = tmp_path / 'run.sh'
    executor.trans_layer = 'tcp'
    executor.port = 2200
    return executor


def test_run_exe_logs_missing_script(tmp_path, monkeypatch):
    executor = make_executor(tmp_path)
    logger = RecordingLogger()
    monkeypatch.setattr(executor_module, 'logger', logger)

    assert executor.run_exe() is None

    assert any(
        'run script does not exist' in message
        and str(executor.run_script) in message
        for message in logger.messages
    )


def test_run_exe_logs_popen_exception_and_permissions(tmp_path, monkeypatch):
    executor = make_executor(tmp_path)
    executor.run_script.write_text('#!/bin/sh\n', encoding='utf-8')
    logger = RecordingLogger()
    monkeypatch.setattr(executor_module, 'logger', logger)
    monkeypatch.setattr(
        executor_module.configs,
        'fuzz_mode',
        'fuzz',
        raising=False,
    )
    monkeypatch.setattr(
        executor_module.configs,
        'server',
        'parent',
        raising=False,
    )

    assert executor.run_exe() is None

    assert any(
        'PermissionError' in message
        and 'executable=False' in message
        for message in logger.messages
    )


def test_logs_exit_code_and_stderr_for_early_exit(tmp_path, monkeypatch):
    executor = make_executor(tmp_path)
    logger = RecordingLogger()
    monkeypatch.setattr(executor_module, 'logger', logger)
    proc = subprocess.Popen(
        ['/bin/sh', '-c', 'echo missing-config >&2; exit 23'],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    proc.wait()

    executor._log_sut_start_failure(
        proc,
        stage='process-exited-before-ready-check',
        attempt=1,
    )

    message = logger.messages[-1]
    assert 'returncode=23' in message
    assert 'stderr=' in message
    assert 'missing-config' in message


def test_logs_socket_timeout_for_running_process(tmp_path, monkeypatch):
    executor = make_executor(tmp_path)
    logger = RecordingLogger()
    monkeypatch.setattr(executor_module, 'logger', logger)
    proc = SimpleNamespace(pid=1234, poll=lambda: None)

    executor._log_sut_start_failure(
        proc,
        stage='socket-readiness-timeout',
        attempt=100,
        detail='service did not become reachable within 10.00s',
    )

    message = logger.messages[-1]
    assert 'process=running' in message
    assert 'endpoint=localhost:2200' in message
    assert 'service did not become reachable' in message
