import threading
from types import SimpleNamespace

import pytest

from voltron.executor import executor as executor_module
from voltron.executor.conversation import Conversation
from voltron.executor.executor import Executor


class RecordingLogger:
    def __init__(self) -> None:
        self.messages = []

    def debug(self, message) -> None:
        self.messages.append(str(message))


def make_executor() -> Executor:
    executor = Executor.__new__(Executor)
    executor.host = "127.0.0.1"
    executor.port = 8080
    executor.stop_event = threading.Event()
    return executor


def test_interact_logs_matching_begin_and_end_boundaries(monkeypatch):
    executor = make_executor()
    logger = RecordingLogger()
    cons = Conversation()
    cons.add_state("PING", "200")
    cons.add_data(b"PING", b"200 OK")
    monkeypatch.setattr(executor_module, "logger", logger)
    monkeypatch.setattr(
        executor,
        "_interact_once",
        lambda *args, **kwargs: (True, cons),
    )

    assert executor.interact([("PING", b"PING")]) == (True, cons)

    assert len(logger.messages) == 2
    begin, end = logger.messages
    assert "[INTERACT.BEGIN]" in begin
    assert "[INTERACT.END]" in end
    assert "outcome='completed'" in end
    assert "recorded_exchanges=1" in end
    begin_id = begin.split("interaction_id='", 1)[1].split("'", 1)[0]
    assert f"interaction_id='{begin_id}'" in end


def test_interact_logs_end_boundary_when_execution_raises(monkeypatch):
    executor = make_executor()
    logger = RecordingLogger()
    monkeypatch.setattr(executor_module, "logger", logger)

    def fail(*args, **kwargs):
        raise RuntimeError("launch failed")

    monkeypatch.setattr(executor, "_interact_once", fail)

    with pytest.raises(RuntimeError, match="launch failed"):
        executor.interact([("PING", b"PING")])

    assert len(logger.messages) == 2
    assert "[INTERACT.BEGIN]" in logger.messages[0]
    assert "[INTERACT.END]" in logger.messages[1]
    assert "outcome='exception'" in logger.messages[1]
    assert "error_type='RuntimeError'" in logger.messages[1]
