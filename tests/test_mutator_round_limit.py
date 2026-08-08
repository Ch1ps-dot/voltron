import threading
import time
from types import SimpleNamespace

import voltron.fuzz as fuzz_module
from voltron.analyzer.analyzer import analyzer
from voltron.configs import configs
from voltron.fuzz import Fuzzer


def test_mutator_limit_freezes_evolution_but_keeps_berserker_running(
    monkeypatch,
):
    stop_event = threading.Event()
    energies = []
    mutation_calls = []
    checkpoints = []

    class RecordingBerserker:
        def __init__(self, *_args, **_kwargs):
            self.calls = 0

        def run(self, energy):
            energies.append(energy)
            self.calls += 1
            if self.calls == 3:
                stop_event.set()
            return {"PING": {"PONG"}}

    class Producer:
        def generator_mutate(self, request_responses, *, iteration):
            mutation_calls.append((request_responses, iteration))
            return []

    fuzzer = Fuzzer.__new__(Fuzzer)
    fuzzer.mapper = SimpleNamespace()
    fuzzer.exe = object()
    fuzzer.producer = Producer()
    fuzzer.guided_scheduling = False
    fuzzer.spec_knowledge = True

    monkeypatch.setattr(fuzz_module, "Berserker", RecordingBerserker)
    monkeypatch.setattr(configs, "time_limit_s", 3600, raising=False)
    monkeypatch.setattr(configs, "mutator_round_limit", 1, raising=False)
    monkeypatch.setattr(analyzer, "start_time", time.time(), raising=False)
    monkeypatch.setattr(analyzer, "stop_reason", None, raising=False)
    monkeypatch.setattr(analyzer, "begin_phase", lambda *_args: None)
    monkeypatch.setattr(analyzer, "end_phase", lambda *_args: None)
    monkeypatch.setattr(analyzer, "collect_results", lambda: None)
    monkeypatch.setattr(analyzer, "reset_automata_cnt", lambda: None)
    monkeypatch.setattr(
        analyzer,
        "record_iteration_state_metrics",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        analyzer,
        "record_generator_checkpoint",
        lambda **kwargs: checkpoints.append(kwargs),
    )
    monkeypatch.setattr(
        analyzer,
        "finalize_generator_metrics",
        lambda **_kwargs: None,
    )

    fuzzer.berserker_fuzz(None, stop_event)

    assert energies == [2000, 2000, 2000]
    assert mutation_calls == [({"PING": {"PONG"}}, 0)]
    marker_rows = [
        row
        for row in checkpoints
        if row["checkpoint_type"] == "mutator_round_limit_reached"
    ]
    assert marker_rows == [{
        "phase": "fuzzing",
        "checkpoint_type": "mutator_round_limit_reached",
        "phase_iteration": 0,
        "iteration_status": "frozen",
        "mutator_round_limit": 1,
        "mutator_rounds_attempted": 1,
        "published_mutator_types": [],
    }]
