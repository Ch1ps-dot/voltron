import signal
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from voltron.analyzer.analyzer import analyzer
from voltron.configs import configs
from voltron.executor.executor import Executor
from voltron.fuzz import Fuzzer


def make_fuzzer() -> Fuzzer:
    fuzzer = Fuzzer.__new__(Fuzzer)
    fuzzer.mode = "fuzz"
    fuzzer.stop_event = threading.Event()
    fuzzer._cleanup_lock = threading.RLock()
    fuzzer._cleanup_done = False
    fuzzer._previous_sigint_handler = None
    fuzzer._signal_handler_installed = False
    fuzzer._worker_threads = []
    fuzzer.mapper = SimpleNamespace(close=lambda: None)
    return fuzzer


def test_first_interrupt_requests_stop_and_raises(monkeypatch):
    fuzzer = make_fuzzer()
    terminated = []
    signal_changes = []
    monkeypatch.setattr(
        fuzzer,
        "_terminate_active_sut",
        lambda sig, timeout: terminated.append((sig, timeout)),
    )
    monkeypatch.setattr(
        "voltron.fuzz.signal.signal",
        lambda sig, handler: signal_changes.append((sig, handler)),
    )

    with pytest.raises(KeyboardInterrupt):
        fuzzer.handle_normal_fuzzer_exit(signal.SIGINT, None)

    assert fuzzer.stop_event.is_set()
    assert terminated == [(signal.SIGTERM, 0.5)]
    assert signal_changes == [(signal.SIGINT, signal.SIG_IGN)]


def test_cleanup_waits_for_cooperative_worker_before_collecting(monkeypatch):
    fuzzer = make_fuzzer()
    events = []

    def worker():
        while not fuzzer.stop_event.is_set():
            time.sleep(0.001)
        events.append("worker-stopped")

    thread = threading.Thread(target=worker, name="test-worker")
    fuzzer._worker_threads = [thread]
    thread.start()
    monkeypatch.setattr(
        fuzzer,
        "_terminate_active_sut",
        lambda sig, timeout: events.append("sut-stopped"),
    )
    monkeypatch.setattr(
        fuzzer,
        "_collect_results",
        lambda: events.append("results-collected"),
    )
    monkeypatch.setattr(
        fuzzer,
        "_restore_signal_handlers",
        lambda: events.append("signal-restored"),
    )

    fuzzer.cleanup()

    assert not thread.is_alive()
    assert events.index("worker-stopped") < events.index("results-collected")
    assert events.count("results-collected") == 1


def test_executor_does_not_start_sut_after_stop_requested(monkeypatch):
    executor = Executor.__new__(Executor)
    executor.stop_event = threading.Event()
    executor.stop_event.set()
    executor.port = 2200
    calls = []
    executor.kill_listeners = lambda port: calls.append("kill-listeners")
    executor.setup_exe = lambda: calls.append("setup")
    executor.run_exe = lambda: calls.append("run")

    assert executor.interact([]) == (False, None)
    assert calls == []


def test_executor_does_not_restart_sut_when_stop_arrives_during_retry(
    monkeypatch,
):
    class ExitedProcess:
        pid = 123
        returncode = 1

        def poll(self):
            return 1

    executor = Executor.__new__(Executor)
    executor.stop_event = threading.Event()
    executor.port = 2200
    executor.setup_time_s = 0
    executor.kill_listeners = lambda port: None
    executor.setup_exe = lambda: None
    run_calls = []

    def run_exe():
        run_calls.append(True)
        executor.stop_event.set()
        return ExitedProcess()

    executor.run_exe = run_exe
    executor._terminate_process_group = lambda *args, **kwargs: None
    executor._log_sut_start_failure = lambda *args, **kwargs: None

    assert executor.interact([]) == (False, None)
    assert len(run_calls) == 1


def test_terminate_process_group_cleans_descendants_after_leader_exit(
    monkeypatch,
):
    class ExitedProcess:
        pid = 4321

        @staticmethod
        def poll():
            return 0

        @staticmethod
        def wait(timeout=None):
            return 0

    executor = Executor.__new__(Executor)
    process_group_exists = True
    signals = []

    def fake_killpg(pgid, sig):
        nonlocal process_group_exists
        assert pgid == 4321
        if sig == 0:
            if not process_group_exists:
                raise ProcessLookupError
            return
        signals.append(sig)
        process_group_exists = False

    monkeypatch.setattr("voltron.executor.executor.os.getpgrp", lambda: 9999)
    monkeypatch.setattr("voltron.executor.executor.os.killpg", fake_killpg)

    executor._terminate_process_group(
        ExitedProcess(),
        signal.SIGTERM,
        timeout=0.1,
    )

    assert signals == [signal.SIGTERM]


def test_terminate_process_group_reaps_leader_without_sigkill_timeout(
    monkeypatch,
):
    terminated = False
    leader_reaped = False
    signals = []

    class Process:
        pid = 5432

        @staticmethod
        def poll():
            nonlocal leader_reaped
            if not terminated:
                return None
            leader_reaped = True
            return 0

        @staticmethod
        def wait(timeout=None):
            return 0

    def fake_killpg(pgid, sig):
        nonlocal terminated
        assert pgid == 5432
        if sig == 0:
            if leader_reaped:
                raise ProcessLookupError
            return
        signals.append(sig)
        terminated = True

    executor = Executor.__new__(Executor)
    monkeypatch.setattr("voltron.executor.executor.os.getpgrp", lambda: 9999)
    monkeypatch.setattr("voltron.executor.executor.os.killpg", fake_killpg)

    executor._terminate_process_group(Process(), signal.SIGTERM, timeout=1)

    assert leader_reaped is True
    assert signals == [signal.SIGTERM]


def test_fuzzer_registers_interrupt_support_before_module_initialization(
    monkeypatch,
):
    observed = {}

    def fake_install(self):
        observed["stop_event_exists"] = hasattr(self, "stop_event")
        self._signal_handler_installed = True

    monkeypatch.setattr(Fuzzer, "_install_signal_handlers", fake_install)
    monkeypatch.setattr(Fuzzer, "load_configs", lambda self: None)
    monkeypatch.setattr(Fuzzer, "module_init", lambda self: None)
    monkeypatch.setattr("atexit.register", lambda callback: None)

    Fuzzer(target_name="demo")

    assert observed["stop_event_exists"] is True
