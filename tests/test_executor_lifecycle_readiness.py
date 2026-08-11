import socket
import subprocess
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from voltron.configs import configs
from voltron.executor.executor import Executor


def make_executor(tmp_path: Path) -> Executor:
    executor = Executor.__new__(Executor)
    executor.setup_script = tmp_path / "setup.sh"
    executor.readiness_script = None
    executor.readiness_adapter = ""
    executor.setup_timeout_s = 1.0
    executor.readiness_timeout_s = 1.0
    executor.socket_readiness_timeout_s = 1.0
    executor.socket_readiness_poll_interval_s = 0.01
    executor.protocol_readiness_successes = 1
    executor.port_release_timeout_s = 0.2
    executor.setup_time_s = 0.01
    executor.sut_deployment = "local"
    executor.stop_event = threading.Event()
    executor._prefetched_initial_response = None
    return executor


def readiness_analyzer():
    return SimpleNamespace(
        lock=threading.RLock(),
        socket_readiness_timeouts=0,
        protocol_readiness_failures=0,
        sut_exited_before_first_send=0,
    )


def write_script(path: Path, body: str) -> None:
    path.write_text(f"#!/bin/sh\nset -eu\n{body}\n", encoding="utf-8")
    path.chmod(0o755)


def test_environment_setup_runs_once_for_repeated_initialization(
    tmp_path,
    monkeypatch,
):
    executor = make_executor(tmp_path)
    count_path = tmp_path / "count"
    write_script(
        executor.setup_script,
        f'printf x >> "{count_path}"\necho environment-ready',
    )
    monkeypatch.setattr(configs, "fuzz_mode", "fuzz", raising=False)

    assert executor.initialize_environment() is True
    assert executor.initialize_environment() is True

    assert count_path.read_text(encoding="utf-8") == "x"
    assert executor.environment_state == "succeeded"
    assert executor.environment_result.stdout.strip() == "environment-ready"


def test_concurrent_environment_initialization_shares_one_result(
    tmp_path,
    monkeypatch,
):
    executor = make_executor(tmp_path)
    count_path = tmp_path / "count"
    write_script(
        executor.setup_script,
        f'sleep 0.1\nprintf x >> "{count_path}"',
    )
    monkeypatch.setattr(configs, "fuzz_mode", "fuzz", raising=False)
    results = []
    threads = [
        threading.Thread(
            target=lambda: results.append(executor.initialize_environment())
        )
        for _ in range(6)
    ]

    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert results == [True] * 6
    assert count_path.read_text(encoding="utf-8") == "x"


def test_setup_failure_is_cached_and_stops_fuzzing(tmp_path, monkeypatch):
    executor = make_executor(tmp_path)
    count_path = tmp_path / "count"
    write_script(
        executor.setup_script,
        f'printf x >> "{count_path}"\necho setup-broken >&2\nexit 23',
    )
    monkeypatch.setattr(configs, "fuzz_mode", "fuzz", raising=False)

    assert executor.initialize_environment() is False
    assert executor.initialize_environment() is False

    assert executor.stop_event.is_set()
    assert count_path.read_text(encoding="utf-8") == "x"
    assert executor.environment_result.stage == "environment-setup-failed"
    assert executor.environment_result.returncode == 23
    assert "setup-broken" in executor.environment_result.stderr


def test_setup_timeout_has_independent_failure_stage(tmp_path, monkeypatch):
    executor = make_executor(tmp_path)
    executor.setup_timeout_s = 0.1
    write_script(executor.setup_script, "sleep 10")
    monkeypatch.setattr(configs, "fuzz_mode", "fuzz", raising=False)

    assert executor.initialize_environment() is False
    assert executor.environment_result.stage == "environment-setup-timeout"
    assert "exceeded" in executor.environment_result.error


def test_replay_remote_and_missing_setup_are_noop_successes(
    tmp_path,
    monkeypatch,
):
    replay = make_executor(tmp_path / "replay")
    monkeypatch.setattr(configs, "fuzz_mode", "replay", raising=False)
    assert replay.initialize_environment() is True

    remote = make_executor(tmp_path / "remote")
    remote.sut_deployment = "remote"
    monkeypatch.setattr(configs, "fuzz_mode", "fuzz", raising=False)
    assert remote.initialize_environment() is True

    missing = make_executor(tmp_path / "missing")
    assert missing.initialize_environment() is True


def test_target_starts_once_per_interaction_without_restarting_setup(
    tmp_path,
    monkeypatch,
):
    executor = make_executor(tmp_path)
    count_path = tmp_path / "setup-count"
    write_script(executor.setup_script, f'printf x >> "{count_path}"')
    monkeypatch.setattr(configs, "fuzz_mode", "fuzz", raising=False)
    executor.port = 2200
    executor.kill_listeners = lambda _port: None
    executor._wait_for_port_release = lambda _port: True
    run_count = []

    class RunningProcess:
        pid = 12345

        @staticmethod
        def poll():
            return None

    executor.run_exe = lambda: run_count.append(True) or RunningProcess()

    assert executor.initialize_environment() is True
    assert executor.start_sut_for_interaction()[0] is True
    assert executor.initialize_environment() is True
    assert executor.start_sut_for_interaction()[0] is True

    assert count_path.read_text(encoding="utf-8") == "x"
    assert len(run_count) == 2


def test_transient_port_cleanup_failure_can_be_retried_without_global_stop(
    tmp_path,
):
    executor = make_executor(tmp_path)
    executor.port = 2200
    executor.kill_listeners = lambda _port: None
    executor._wait_for_port_release = lambda _port: False
    executor._log_sut_start_failure = lambda *_args, **_kwargs: None

    started, proc = executor.start_sut_for_interaction(stop_on_failure=False)

    assert started is False
    assert proc is None
    assert not executor.stop_event.is_set()

    executor.start_sut_for_interaction()
    assert executor.stop_event.is_set()


def serve_once(handler):
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    port = server.getsockname()[1]

    def run():
        try:
            connection, _ = server.accept()
            with connection:
                handler(connection)
        finally:
            server.close()

    thread = threading.Thread(target=run)
    thread.start()
    return port, thread


def test_daap_readiness_uses_independent_valid_http_exchange():
    received = []

    def handler(connection):
        received.append(connection.recv(4096))
        connection.sendall(
            b"HTTP/1.1 200 OK\r\nContent-Length: 0\r\n\r\n"
        )

    port, thread = serve_once(handler)
    script = (
        Path(__file__).parents[1]
        / "config/subjects/forked-daapd/ready.sh"
    )
    result = subprocess.run(
        [script, "127.0.0.1", str(port), "1"],
        capture_output=True,
        text=True,
        timeout=2,
    )
    thread.join(timeout=1)

    assert result.returncode == 0, result.stderr
    assert received and received[0].startswith(b"GET /server-info HTTP/1.1")
    assert "DAAP ready" in result.stdout


def configure_active_ftp_readiness(executor):
    executor.readiness_adapter = "ftp_banner_active_socket"
    executor.host = "127.0.0.1"
    executor.port = 21
    executor.trans_layer = "tcp"
    executor.parser_func = lambda response: response[:3]
    executor.unable_parse_request = set()


def test_ftp_readiness_reuses_and_preserves_active_fuzz_socket(tmp_path):
    executor = make_executor(tmp_path)
    configure_active_ftp_readiness(executor)
    client, server = socket.socketpair()
    client.setblocking(False)
    banner = b"220-test server\r\n220 ready\r\n"
    server.sendall(banner)

    try:
        assert executor.run_subject_readiness(client) is True
        assert executor.last_readiness_result.stage == (
            "protocol-readiness-complete"
        )

        executor.net_recv = lambda **_kwargs: pytest.fail(
            "cached banner must not be read from the socket twice"
        )
        resp_code, resp_data = executor._receive_initial_response(
            client,
            poll_timeout_ms=100,
            show_fuzz_ui=False,
        )
        assert (resp_code, resp_data) == ("220", banner)

        server.setblocking(False)
        with pytest.raises(BlockingIOError):
            server.recv(4096)
    finally:
        client.close()
        server.close()


def test_ftp_readiness_rejects_non_220_banner(tmp_path):
    executor = make_executor(tmp_path)
    configure_active_ftp_readiness(executor)
    client, server = socket.socketpair()
    client.setblocking(False)
    server.sendall(b"500 service unavailable\r\n")

    try:
        assert executor.run_subject_readiness(client) is False
        assert executor.last_readiness_result.stage == (
            "protocol-readiness-failed"
        )
        assert "invalid FTP banner" in executor.last_readiness_result.error
        assert executor._prefetched_initial_response is None
    finally:
        client.close()
        server.close()


def test_ftp_readiness_timeout_has_independent_failure_stage(tmp_path):
    executor = make_executor(tmp_path)
    configure_active_ftp_readiness(executor)
    executor.readiness_timeout_s = 0.02
    client, server = socket.socketpair()
    client.setblocking(False)

    try:
        assert executor.run_subject_readiness(client) is False
        assert executor.last_readiness_result.stage == (
            "protocol-readiness-timeout"
        )
    finally:
        client.close()
        server.close()


def test_protocol_readiness_failure_is_captured(tmp_path):
    executor = make_executor(tmp_path)
    executor.host = "127.0.0.1"
    executor.port = 1
    executor.readiness_script = tmp_path / "ready.sh"
    write_script(executor.readiness_script, "echo invalid-protocol >&2\nexit 9")

    assert executor.run_subject_readiness() is False
    assert executor.last_readiness_result.stage == "protocol-readiness-failed"
    assert executor.last_readiness_result.returncode == 9
    assert "invalid-protocol" in executor.last_readiness_result.stderr


def test_protocol_readiness_requires_consecutive_successes(tmp_path):
    executor = make_executor(tmp_path)
    executor.analyzer = readiness_analyzer()
    executor.protocol_readiness_successes = 3
    executor.readiness_timeout_s = 0.1
    executor.socket_readiness_poll_interval_s = 0.001
    executor._should_stop = lambda: False
    outcomes = iter([False, True, True, True])
    executor.run_subject_readiness = lambda _sock, timeout_s=None: next(outcomes)

    assert executor.wait_for_subject_readiness() is True
    assert executor.analyzer.protocol_readiness_failures == 1


def test_socket_readiness_timeout_uses_explicit_budget(tmp_path):
    executor = make_executor(tmp_path)
    executor.analyzer = readiness_analyzer()
    executor.socket_readiness_timeout_s = 0.03
    executor.socket_readiness_poll_interval_s = 0.005
    executor._is_remote_deployment = lambda: False
    executor.setup_socket = lambda: None
    executor._log_sut_start_failure = lambda *_args, **_kwargs: None

    class RunningProcess:
        @staticmethod
        def poll():
            return None

    started = time.monotonic()
    assert executor._wait_for_socket_readiness(RunningProcess()) is None
    elapsed = time.monotonic() - started

    assert 0.02 <= elapsed < 0.2
    assert executor.analyzer.socket_readiness_timeouts == 1
