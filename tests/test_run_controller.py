import threading

from voltron.executor.executor import Executor
from voltron.run_controller import RunController
from voltron.scheduler.berserker import Berserker
from voltron.analyzer.analyzer import analyzer


def test_run_controller_has_one_immutable_deadline_and_requests_once():
    now = [10.0]
    reasons = []
    stop_event = threading.Event()

    def request_stop(reason):
        reasons.append(reason)
        stop_event.set()

    controller = RunController(
        5,
        stop_event,
        request_stop,
        clock=lambda: now[0],
    )

    assert controller.elapsed_s() == 0.0
    assert controller.remaining_s() == 5.0
    now[0] = 15.0
    assert controller.should_stop() is True
    assert controller.remaining_s() == 0.0
    assert controller.should_stop() is True
    assert reasons == ['deadline']


def test_run_controller_watcher_signals_the_shared_stop_event():
    stop_event = threading.Event()
    reasons = []
    controller = RunController(
        0.02,
        stop_event,
        lambda reason: reasons.append(reason) or stop_event.set(),
    )

    controller.start()

    assert stop_event.wait(1)
    controller.close()
    assert reasons == ['deadline']


def test_berserker_stops_before_a_second_interaction_after_deadline(
    monkeypatch,
):
    class Mapper:
        request_types = {'PING'}
        req_dep = {}
        mutators = {}

    class Controller:
        expired = False

        def should_stop(self):
            return self.expired

    class ExecutorDouble:
        def __init__(self, controller):
            self.controller = controller
            self.calls = 0

        def interact(self, *_args, **_kwargs):
            self.calls += 1
            self.controller.expired = True
            return False, None

    controller = Controller()
    executor = ExecutorDouble(controller)
    monkeypatch.setattr(analyzer, 'set_progress', lambda *_args, **_kwargs: None)
    monkeypatch.setattr(analyzer, 'clean_progress', lambda: None)
    berserker = Berserker(
        Mapper(),
        executor,
        None,
        use_guidance=False,
        controller=controller,
    )
    berserker.select_base_state = lambda: []
    berserker.select_suffix = lambda: []

    berserker.run(10)

    assert executor.calls == 1


def test_executor_poll_returns_when_controller_stops_run():
    class Controller:
        checks = 0

        def should_stop(self):
            self.checks += 1
            return self.checks >= 3

    class Poller:
        def __init__(self):
            self.waits = []

        def poll(self, timeout_ms):
            self.waits.append(timeout_ms)
            return []

    executor = Executor.__new__(Executor)
    executor.stop_event = threading.Event()
    executor.run_controller = Controller()
    poller = Poller()

    assert executor._poll_with_stop(poller, 1000) is None
    assert poller.waits
    assert max(poller.waits) <= 100
