from pathlib import Path
from types import SimpleNamespace
import threading
import time

import pytest

from voltron.analyzer.analyzer import analyzer
from voltron.configs import configs
from voltron.executor.conversation import Conversation
from voltron.fuzz import Fuzzer
from voltron.llm.chatter import LLMDeadlineExceeded
from voltron.learner.equ_oracle import EquOracle
from voltron.learner.mem_oracle import MembershipOracle
from voltron.learner.mlstar import (
    MealyLstar,
    ModelLearningStopped,
    ModelLearningThresholdReached,
)
from voltron.learner.automata import MealyMachine
from voltron.learner.partial_guidance import (
    ModelLearningThreshold,
    PartialStateGraph,
    PartialTrace,
    PartialTraceRecorder,
)
from voltron.scheduler.berserker import Berserker
from voltron.synthesizer.synthesizer import AsyncProducer


def conversation(*steps: tuple[str, bytes, str, bytes]) -> Conversation:
    result = Conversation()
    result.add_state('-', '220')
    result.add_data(b'', b'220 ready\r\n')
    for symbol, request, response, raw_response in steps:
        result.add_state(symbol, response)
        result.add_data(request, raw_response)
    return result


def test_input_output_scaled_threshold_reaches_after_four_no_growth_mqs():
    recorder = PartialTraceRecorder()
    threshold = ModelLearningThreshold(['PING'])
    trace = conversation(('PING', b'PING\r\n', 'PONG', b'PONG\r\n'))

    assert threshold.observe(recorder, recorder.observe(trace)) is False
    assert threshold.threshold == 4
    assert threshold.observe(recorder, recorder.observe(trace)) is False
    assert threshold.observe(recorder, recorder.observe(trace)) is False
    assert threshold.observe(recorder, recorder.observe(trace)) is False
    assert threshold.observe(recorder, recorder.observe(trace)) is True
    assert threshold.no_growth_mq == 4
    assert recorder.graph.seed_sequences() == [[('PING', b'PING\r\n')]]


def test_input_output_scaled_threshold_uses_higher_large_alphabet_cap():
    recorder = PartialTraceRecorder()
    threshold = ModelLearningThreshold([f'REQ{i}' for i in range(48)])
    recorder.graph.executed_symbols.update(threshold.alphabet)
    recorder.graph.response_symbols.update(f'RES{i}' for i in range(22))

    assert threshold.observe(recorder, pair_grew=False) is False
    assert threshold.round_size == 48
    assert threshold.rounds == 10
    assert threshold.threshold == 480


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

    # The initial six table cells are fully drained first.  With the higher
    # conservative threshold, four further no-growth MQs are needed to mark
    # the table as stalled.
    mq.query(('A',))
    mq.query(('B',))
    mq.query(('A',))
    mq.query(('B',))
    assert threshold.reached is True
    # S={-}, E={A,B} requires six initial cells, which remain intact when the
    # threshold is later reached.
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


def _hypothesis(model_id: str) -> MealyMachine:
    return MealyMachine(
        id=model_id,
        states={0},
        alphabet={'PING'},
        delta={(0, 'PING'): 0},
        output={(0, 'PING'): 'PONG'},
        start=0,
        table=([], [], {}),
    )


def _threshold_mq(version: int):
    recorder = PartialTraceRecorder()
    recorder.observe(
        conversation(('PING', b'PING\r\n', 'PONG', b'PONG\r\n'))
    )
    return SimpleNamespace(trace_recorder=recorder, version=version)


def _prepare_relearning_fuzzer(tmp_path, monkeypatch):
    class Mapper:
        cur_parser = 'parser-v1'
        generators = {'PING': ['generator-v1']}

        def register_mapper(self, hypothesis):
            hypothesis.map = {}

    fuzzer = Fuzzer.__new__(Fuzzer)
    fuzzer.mapper = Mapper()
    fuzzer.target_name = 'mock'
    fuzzer.spec_knowledge = True
    fuzzer.stop_event = threading.Event()
    monkeypatch.setattr(configs, 'models_path', tmp_path / 'models', raising=False)
    monkeypatch.setattr(configs, 'results_path', tmp_path / 'results', raising=False)
    monkeypatch.setattr(configs, 'time_limit_s', 60, raising=False)
    monkeypatch.setattr(configs, 'threshold_relearn_limit', 3, raising=False)
    monkeypatch.setattr(configs, 'bootstrap_partial_evolution', True, raising=False)
    monkeypatch.setattr(analyzer, 'start_time', time.time(), raising=False)
    monkeypatch.setattr(analyzer, 'iter', 0, raising=False)
    monkeypatch.setattr(
        analyzer,
        'record_model_learning_iteration',
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        analyzer,
        'record_generator_checkpoint',
        lambda **_kwargs: None,
    )
    return fuzzer


def test_threshold_before_first_h_bootstraps_partial_then_relearns(
    tmp_path,
    monkeypatch,
):
    table = SimpleNamespace(S={('-',)}, E={('PING',)}, T={})
    learner_calls = {'count': 0}

    class Learner:
        def __init__(self, mq, *_args):
            self.mq = mq

        def run(self, model_id):
            learner_calls['count'] += 1
            if learner_calls['count'] == 1:
                raise ModelLearningThresholdReached(table)
            fuzzer.stop_event.set()
            analyzer.cur_res_types_cnt = {'PONG': 1}
            analyzer.cur_resp_trans_cnt = {'edge': 1}
            return _hypothesis(model_id)

    class Producer:
        def __init__(self):
            self.partial_calls = []
            self.complete_calls = []

        def generator_evo_from_partial(self, partial):
            self.partial_calls.append(partial)
            return ['PING']

        def generator_evo(self, hypothesis):
            self.complete_calls.append(hypothesis)
            return ['PING']

        def capture_current_equipment(self, parser):
            return {'PING': 'generator-v1'}, parser

    monkeypatch.setattr('voltron.fuzz.MealyLstar', Learner)
    fuzzer = _prepare_relearning_fuzzer(tmp_path, monkeypatch)
    fuzzer.producer = Producer()
    oracle_versions = iter([_threshold_mq(1), _threshold_mq(2)])
    fuzzer._learning_oracle_factory = lambda: (next(oracle_versions), object())
    initial_mq = _threshold_mq(0)

    result = fuzzer.model_learning(initial_mq, object(), fuzzer.stop_event)

    assert result is not None
    assert len(fuzzer.producer.partial_calls) == 1
    assert len(fuzzer.producer.complete_calls) == 1
    assert learner_calls['count'] == 2
    assert (tmp_path / 'models' / 'partial_guidance' / 'iteration_0.pkl').is_file()


def test_threshold_after_complete_h_evolves_from_best_h(
    tmp_path,
    monkeypatch,
):
    table = SimpleNamespace(S={('-',)}, E={('PING',)}, T={})
    learner_calls = {'count': 0}

    class Learner:
        def __init__(self, *_args):
            pass

        def run(self, model_id):
            learner_calls['count'] += 1
            if learner_calls['count'] == 2:
                raise ModelLearningThresholdReached(table)
            analyzer.cur_res_types_cnt = {'PONG': 1}
            analyzer.cur_resp_trans_cnt = {'edge': 1}
            if learner_calls['count'] == 3:
                fuzzer.stop_event.set()
            return _hypothesis(model_id)

    class Producer:
        def __init__(self):
            self.complete_calls = []
            self.partial_calls = 0

        def generator_evo(self, hypothesis):
            self.complete_calls.append(hypothesis.id)
            return ['PING']

        def generator_evo_from_partial(self, _partial):
            self.partial_calls += 1
            return ['PING']

        def capture_current_equipment(self, parser):
            return {'PING': 'generator-v1'}, parser

    monkeypatch.setattr('voltron.fuzz.MealyLstar', Learner)
    fuzzer = _prepare_relearning_fuzzer(tmp_path, monkeypatch)
    fuzzer.producer = Producer()
    fuzzer._learning_oracle_factory = lambda: (_threshold_mq(1), object())

    result = fuzzer.model_learning(
        _threshold_mq(0), object(), fuzzer.stop_event
    )

    assert result is not None
    # Once after the first complete H, then again to recover from threshold.
    assert fuzzer.producer.complete_calls == ['0', '0']
    assert fuzzer.producer.partial_calls == 0


def test_threshold_relearning_exhausts_only_after_configured_retries(
    tmp_path,
    monkeypatch,
):
    table = SimpleNamespace(S={('-',)}, E={('PING',)}, T={})

    class Learner:
        def __init__(self, *_args):
            pass

        def run(self, _model_id):
            raise ModelLearningThresholdReached(table)

    class Producer:
        def __init__(self):
            self.partial_calls = 0

        def generator_evo_from_partial(self, _partial):
            self.partial_calls += 1
            return ['PING']

    monkeypatch.setattr('voltron.fuzz.MealyLstar', Learner)
    fuzzer = _prepare_relearning_fuzzer(tmp_path, monkeypatch)
    fuzzer.producer = Producer()
    monkeypatch.setattr(configs, 'threshold_relearn_limit', 2, raising=False)
    fuzzer._learning_oracle_factory = lambda: (_threshold_mq(1), object())

    result = fuzzer.model_learning(
        _threshold_mq(0), object(), fuzzer.stop_event
    )

    assert result is None
    assert fuzzer.producer.partial_calls == 2
    assert analyzer.iter == 3
    assert fuzzer.learning_outcome == 'partial_after_retry_exhausted'


def test_threshold_relearning_keeps_running_after_explicit_no_change(
    tmp_path,
    monkeypatch,
):
    table = SimpleNamespace(S={('-',)}, E={('PING',)}, T={})

    class Learner:
        def __init__(self, *_args):
            pass

        def run(self, _model_id):
            raise ModelLearningThresholdReached(table)

    class Producer:
        def __init__(self):
            self.partial_calls = 0
            self._last_generator_evolution_outcome = {}

        def generator_evo_from_partial(self, _partial):
            self.partial_calls += 1
            self._last_generator_evolution_outcome = {
                'attempted': 1,
                'changed': 0,
                'no_change': 1,
                'failed': 0,
            }
            return []

    monkeypatch.setattr('voltron.fuzz.MealyLstar', Learner)
    fuzzer = _prepare_relearning_fuzzer(tmp_path, monkeypatch)
    fuzzer.producer = Producer()
    monkeypatch.setattr(configs, 'threshold_relearn_limit', 2, raising=False)
    monkeypatch.setattr(configs, 'run_controller', None, raising=False)
    monkeypatch.setattr(analyzer, 'stop_reason', None, raising=False)
    fuzzer._learning_oracle_factory = lambda: (_threshold_mq(1), object())

    result = fuzzer.model_learning(
        _threshold_mq(0), object(), fuzzer.stop_event
    )

    assert result is None
    assert fuzzer.producer.partial_calls == 2
    assert not fuzzer.stop_event.is_set()
    assert analyzer.stop_reason is None
    assert fuzzer.learning_outcome == 'partial_after_retry_exhausted'


def test_threshold_evolution_deadline_is_not_model_learning_failure(
    tmp_path,
    monkeypatch,
):
    table = SimpleNamespace(S={('-',)}, E={('PING',)}, T={})

    class Learner:
        def __init__(self, *_args):
            pass

        def run(self, _model_id):
            raise ModelLearningThresholdReached(table)

    class Producer:
        def generator_evo_from_partial(self, _partial):
            raise LLMDeadlineExceeded('deadline')

    monkeypatch.setattr('voltron.fuzz.MealyLstar', Learner)
    fuzzer = _prepare_relearning_fuzzer(tmp_path, monkeypatch)
    fuzzer.producer = Producer()
    monkeypatch.setattr(analyzer, 'stop_reason', None, raising=False)

    assert fuzzer.model_learning(_threshold_mq(0), object(), fuzzer.stop_event) is None
    assert fuzzer.stop_event.is_set()
    assert analyzer.stop_reason == 'deadline'


def test_learning_deadline_persists_partial_before_threshold(
    tmp_path,
    monkeypatch,
):
    table = SimpleNamespace(S={('-',)}, E={('PING',)}, T={})

    class Learner:
        def __init__(self, *_args):
            self.table = table

        def run(self, _model_id):
            analyzer.request_stop('deadline', fuzzer.stop_event)
            raise ModelLearningStopped('deadline')

    monkeypatch.setattr('voltron.fuzz.MealyLstar', Learner)
    fuzzer = _prepare_relearning_fuzzer(tmp_path, monkeypatch)
    monkeypatch.setattr(analyzer, 'stop_reason', None, raising=False)
    initial_mq = _threshold_mq(0)

    assert fuzzer.model_learning(initial_mq, object(), fuzzer.stop_event) is None
    assert fuzzer.learning_outcome == 'deadline_partial'
    assert fuzzer.partial_guidance.reason == 'deadline_partial'
    assert fuzzer.partial_guidance.seed_sequences()


def test_partial_generator_evolution_uses_sparse_types_without_fake_h(
    tmp_path,
    monkeypatch,
):
    graph = PartialStateGraph(fingerprint={'target': 'mock'})
    graph.traces.append(
        PartialTrace(
            messages=(('PING', b'PING\r\n'),),
            responses=('PONG',),
        )
    )
    graph.request_response_pairs = {
        ('PING', 'PONG'),
        ('STATUS', 'OK'),
        ('STATUS', 'BUSY'),
    }
    info_path = tmp_path / 'info.md'
    info_path.write_text('protocol notes', encoding='utf-8')
    captured = {}

    producer = AsyncProducer.__new__(AsyncProducer)
    producer.req_types = {'PING', 'STATUS'}
    producer.info_path = info_path

    async def fake_evolve(doc_info, machine, msg_types, trace_hints):
        captured.update(
            doc_info=doc_info,
            machine=machine,
            msg_types=msg_types,
            trace_hints=trace_hints,
        )
        return [('PING', "def generate():\n    return b'PING\\r\\n'\n")]

    producer._generator_evo_async = fake_evolve
    producer._save_evolved_generators = lambda _results: ['PING']
    monkeypatch.setattr(analyzer, 'set_progress', lambda *_args: None)
    monkeypatch.setattr(analyzer, 'clean_progress', lambda: None)

    result = producer.generator_evo_from_partial(graph)

    assert result == ['PING']
    assert captured['machine'] is None
    assert captured['msg_types'] == {'PING'}
    assert 'observed request path: PING' in next(
        iter(captured['trace_hints']['PING'])
    )
