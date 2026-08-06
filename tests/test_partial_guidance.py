from pathlib import Path
from types import SimpleNamespace
import threading
import time

import pytest

from voltron.analyzer.analyzer import analyzer
from voltron.configs import configs
from voltron.executor.conversation import Conversation
from voltron.fuzz import Fuzzer
from voltron.learner.equ_oracle import EquOracle
from voltron.learner.mem_oracle import MembershipOracle
from voltron.learner.mlstar import (
    MealyLstar,
    ModelLearningThresholdReached,
)
from voltron.learner.partial_guidance import (
    ModelLearningThreshold,
    PartialStateGraph,
    PartialTrace,
    PartialTraceRecorder,
)
from voltron.scheduler.berserker import Berserker


def conversation(*steps: tuple[str, bytes, str, bytes]) -> Conversation:
    result = Conversation()
    result.add_state('-', '220')
    result.add_data(b'', b'220 ready\r\n')
    for symbol, request, response, raw_response in steps:
        result.add_state(symbol, response)
        result.add_data(request, raw_response)
    return result


def test_input_output_scaled_threshold_reaches_after_two_no_growth_mqs():
    recorder = PartialTraceRecorder()
    threshold = ModelLearningThreshold(['PING'])
    trace = conversation(('PING', b'PING\r\n', 'PONG', b'PONG\r\n'))

    assert threshold.observe(recorder, recorder.observe(trace)) is False
    assert threshold.threshold == 2
    assert threshold.observe(recorder, recorder.observe(trace)) is False
    assert threshold.observe(recorder, recorder.observe(trace)) is True
    assert threshold.no_growth_mq == 2
    assert recorder.graph.seed_sequences() == [[('PING', b'PING\r\n')]]


def test_partial_recorder_rejects_abnormal_conversations():
    recorder = PartialTraceRecorder()
    bad = conversation(('PING', b'PING\r\n', 'TIMEOUT', b''))

    assert recorder.observe(bad) is False
    assert recorder.graph.traces == []


def test_real_observation_table_drains_before_threshold_partial_exit(
    monkeypatch,
):
    class Mapper:
        request_types = {'A', 'B'}

        def select_generators(self, word, **_kwargs):
            return [
                (symbol, symbol.encode())
                for symbol in word
                if symbol != '-'
            ]

    class Executor:
        def interact(self, messages):
            result = Conversation()
            result.add_state('-', '220')
            result.add_data(b'', b'220 ready\r\n')
            for symbol, request in messages:
                result.add_state(symbol, 'OK')
                result.add_data(request, b'OK\r\n')
            return True, result

        def save_cons(self, _conversation):
            return True

    mapper = Mapper()
    monkeypatch.setattr(configs, 'time_limit_s', 60, raising=False)
    monkeypatch.setattr(analyzer, 'start_time', time.time(), raising=False)
    recorder = PartialTraceRecorder()
    threshold = ModelLearningThreshold(mapper.request_types)
    mq = MembershipOracle(
        mapper,
        Executor(),
        trace_recorder=recorder,
        threshold_tracker=threshold,
    )
    learner = MealyLstar(mq, EquOracle(mapper, Executor()), threading.Event())

    assert threshold.reached is True
    # S={-}, E={A,B} requires six initial cells.  The threshold is reached
    # during that fill, but the current fixed table is still fully drained.
    assert set(learner.table.T) == {('-',), ('-', 'A'), ('-', 'B')}
    assert all(len(row) == 2 for row in learner.table.T.values())
    with pytest.raises(ModelLearningThresholdReached):
        learner.run('partial')


def test_berserker_uses_partial_trace_as_concrete_prefix():
    graph = PartialStateGraph(
        fingerprint={'target': 'mock'},
    )
    graph.traces.append(
        PartialTrace(
            messages=(('PING', b'PING\r\n'),),
            responses=('PONG',),
        )
    )

    class Mapper:
        request_types = {'PING'}
        req_dep = {}

    berserker = Berserker(
        Mapper(),
        object(),
        None,
        partial_guidance=graph,
    )
    berserker.rand = SimpleNamespace(
        random=lambda: 0.0,
        choice=lambda values: values[0],
    )

    assert berserker.select_base_state() == [('PING', b'PING\r\n')]
    assert berserker.selected_partial_prefix is True


def test_berserker_partial_guidance_reaches_normal_executor_path(monkeypatch):
    graph = PartialStateGraph(fingerprint={'target': 'mock'})
    graph.traces.append(
        PartialTrace(
            messages=(('PING', b'PING\r\n'),),
            responses=('PONG',),
        )
    )
    seen: list[list[tuple[str, bytes]]] = []

    class Mapper:
        request_types = {'PING'}
        req_dep = {}
        mutators = {}

    class Executor:
        def interact(self, messages, **_kwargs):
            seen.append(messages)
            return True, conversation(
                *[
                    (symbol, request, 'PONG', b'PONG\r\n')
                    for symbol, request in messages
                ]
            )

        def save_cons(self, _conversation):
            return True

    monkeypatch.setattr(analyzer, 'set_progress', lambda *_args, **_kwargs: None)
    monkeypatch.setattr(analyzer, 'clean_progress', lambda: None)
    berserker = Berserker(
        Mapper(),
        Executor(),
        None,
        partial_guidance=graph,
    )
    berserker.rand = SimpleNamespace(
        random=lambda: 0.0,
        choice=lambda values: values[0],
    )
    berserker.select_mutated_seq = lambda: []
    berserker.select_suffix = lambda: []

    berserker.run(1)

    assert seen
    assert all(sequence[:1] == [('PING', b'PING\r\n')] for sequence in seen)


def test_model_learning_threshold_persists_partial_graph(tmp_path, monkeypatch):
    recorder = PartialTraceRecorder()
    recorder.observe(conversation(('PING', b'PING\r\n', 'PONG', b'PONG\r\n')))
    table = SimpleNamespace(S={('-',)}, E={('PING',)}, T={})

    class ThresholdLearner:
        def __init__(self, *_args):
            pass

        def run(self, _model_id):
            raise ModelLearningThresholdReached(table)

    monkeypatch.setattr('voltron.fuzz.MealyLstar', ThresholdLearner)
    monkeypatch.setattr(configs, 'models_path', tmp_path / 'models', raising=False)
    monkeypatch.setattr(configs, 'results_path', tmp_path / 'results', raising=False)
    monkeypatch.setattr(configs, 'time_limit_s', 60, raising=False)
    monkeypatch.setattr(analyzer, 'start_time', time.time(), raising=False)
    monkeypatch.setattr(analyzer, 'iter', 0, raising=False)

    class Mapper:
        cur_parser = 'parser-v1'
        generators = {'PING': 'generator-v1'}

    fuzzer = Fuzzer.__new__(Fuzzer)
    fuzzer.mapper = Mapper()
    fuzzer.target_name = 'mock'
    fuzzer.spec_knowledge = False
    fuzzer.stop_event = threading.Event()

    result = fuzzer.model_learning(
        SimpleNamespace(trace_recorder=recorder),
        object(),
        fuzzer.stop_event,
    )

    assert result is None
    assert fuzzer.partial_guidance.reason == 'threshold_drained_partial'
    assert (tmp_path / 'models' / 'partial_guidance.pkl').is_file()
    assert (tmp_path / 'results' / 'partial_guidance.pkl').is_file()
