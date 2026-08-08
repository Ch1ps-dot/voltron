import asyncio
from types import SimpleNamespace
import threading
import time

import pytest

import voltron.fuzz as fuzz_module
from voltron.analyzer.analyzer import analyzer
from voltron.configs import configs
from voltron.fuzz import Fuzzer
from voltron.llm.chatter import AsyncChater, LLMDeadlineExceeded
from voltron.synthesizer.synthesizer import AsyncProducer
from voltron.learner.partial_guidance import PartialStateGraph, PartialTrace


def test_llm_request_is_not_started_after_fuzz_deadline(monkeypatch):
    calls = []

    async def create(**_kwargs):
        calls.append(True)
        return None

    stop_event = threading.Event()
    chatter = AsyncChater.__new__(AsyncChater)
    chatter.clt = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(create=create),
        )
    )
    chatter.model = "test-model"

    monkeypatch.setattr(configs, "time_limit_s", 1, raising=False)
    monkeypatch.setattr(analyzer, "start_time", time.time() - 2, raising=False)
    monkeypatch.setattr(analyzer, "stop_event", stop_event, raising=False)

    with pytest.raises(LLMDeadlineExceeded):
        asyncio.run(chatter.chat_llm("prompt", "test"))

    assert calls == []
    assert stop_event.is_set()


def test_llm_deadline_uses_run_controller_when_present(monkeypatch):
    calls = []
    deadline_requests = []

    async def create(**_kwargs):
        calls.append(True)
        return None

    chatter = AsyncChater.__new__(AsyncChater)
    chatter.clt = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(create=create),
        )
    )
    chatter.model = 'test-model'
    controller = SimpleNamespace(
        remaining_s=lambda: 0.0,
        request_stop=lambda reason: deadline_requests.append(reason),
    )
    monkeypatch.setattr(configs, 'run_controller', controller, raising=False)

    with pytest.raises(LLMDeadlineExceeded):
        asyncio.run(chatter.chat_llm('prompt', 'test'))

    assert calls == []
    assert deadline_requests == ['deadline']


def test_model_learning_returns_cleanly_when_llm_deadline_is_reached(
    tmp_path,
    monkeypatch,
):
    class DeadlineLearning:
        def __init__(self, *_args):
            pass

        def run(self, _model_id):
            raise LLMDeadlineExceeded("deadline")

    fuzzer = Fuzzer.__new__(Fuzzer)
    fuzzer.stop_event = threading.Event()

    monkeypatch.setattr(configs, "models_path", tmp_path, raising=False)
    monkeypatch.setattr(fuzz_module, "MealyLstar", DeadlineLearning)
    monkeypatch.setattr(analyzer, "iter", 0, raising=False)

    assert fuzzer.model_learning(object(), object(), fuzzer.stop_event) is None
    assert fuzzer.stop_event.is_set()


def test_parser_generation_does_not_retry_after_llm_deadline():
    class DeadlineChater:
        async def llm_parser_gen(self, **_kwargs):
            raise LLMDeadlineExceeded("deadline")

    producer = AsyncProducer.__new__(AsyncProducer)
    producer.chater = DeadlineChater()
    producer.rfcp = SimpleNamespace(pro_name="example")
    producer._primary_response_field_info = lambda: "response fields"
    producer._response_type_rules_info = lambda: "rules"

    with pytest.raises(LLMDeadlineExceeded):
        asyncio.run(producer._parser_gen_async())


def test_berserker_fuzz_uses_energy_2000(monkeypatch):
    stop_event = threading.Event()
    energies = []

    class RecordingBerserker:
        def __init__(self, *_args, **_kwargs):
            pass

        def run(self, energy):
            energies.append(energy)
            stop_event.set()
            return []

    fuzzer = Fuzzer.__new__(Fuzzer)
    fuzzer.mapper = SimpleNamespace()
    fuzzer.exe = object()
    fuzzer.guided_scheduling = False
    fuzzer.spec_knowledge = False

    monkeypatch.setattr(fuzz_module, "Berserker", RecordingBerserker)
    monkeypatch.setattr(configs, "time_limit_s", 3600, raising=False)
    monkeypatch.setattr(analyzer, "start_time", time.time(), raising=False)
    monkeypatch.setattr(analyzer, "cur_res_types_cnt", {}, raising=False)
    monkeypatch.setattr(analyzer, "begin_phase", lambda *_args: None)
    monkeypatch.setattr(analyzer, "end_phase", lambda *_args: None)
    monkeypatch.setattr(analyzer, "collect_results", lambda: None)
    monkeypatch.setattr(analyzer, "reset_automata_cnt", lambda: None)
    monkeypatch.setattr(
        analyzer,
        "record_generator_checkpoint",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        analyzer,
        "finalize_generator_metrics",
        lambda **_kwargs: None,
    )

    fuzzer.berserker_fuzz(None, stop_event)

    assert energies == [2000]


def test_state_fuzz_does_not_start_berserker_after_model_timeout(
    tmp_path,
    monkeypatch,
):
    stop_event = threading.Event()
    fuzzer = Fuzzer.__new__(Fuzzer)
    fuzzer.stop_event = stop_event
    fuzzer.state_learning = True
    fuzzer.spec_knowledge = True
    fuzzer.mapper = SimpleNamespace()
    fuzzer.exe = object()

    monkeypatch.setattr(configs, "models_path", tmp_path, raising=False)
    monkeypatch.setattr(fuzz_module, "MembershipOracle", lambda **_kwargs: object())
    monkeypatch.setattr(fuzz_module, "EquOracle", lambda **_kwargs: object())
    monkeypatch.setattr(
        fuzzer,
        "model_learning",
        lambda *_args: stop_event.set() or None,
    )
    monkeypatch.setattr(
        fuzzer,
        "berserker_fuzz",
        lambda *_args: pytest.fail("berserker must not start after timeout"),
    )
    monkeypatch.setattr(analyzer, "begin_phase", lambda *_args: None)
    monkeypatch.setattr(analyzer, "end_phase", lambda *_args: None)
    monkeypatch.setattr(
        analyzer,
        "record_generator_checkpoint",
        lambda **_kwargs: None,
    )

    fuzzer.state_fuzz(stop_event)

    assert stop_event.is_set()


def test_state_fuzz_keeps_partial_guidance_but_does_not_reset_deadline(
    tmp_path,
    monkeypatch,
):
    stop_event = threading.Event()
    graph = PartialStateGraph(fingerprint={'target': 'mock'})
    graph.traces.append(
        PartialTrace(
            messages=(('PING', b'PING\r\n'),),
            responses=('PONG',),
        )
    )
    fuzzer = Fuzzer.__new__(Fuzzer)
    fuzzer.stop_event = stop_event
    fuzzer.state_learning = True
    fuzzer.spec_knowledge = True
    fuzzer.guided_scheduling = True
    fuzzer.mapper = SimpleNamespace()
    fuzzer.exe = object()
    started = time.time() - 10

    monkeypatch.setattr(configs, 'models_path', tmp_path, raising=False)
    monkeypatch.setattr(fuzz_module, 'MembershipOracle', lambda **_kwargs: object())
    monkeypatch.setattr(fuzz_module, 'EquOracle', lambda **_kwargs: object())
    monkeypatch.setattr(
        fuzzer,
        'model_learning',
        lambda *_args: setattr(fuzzer, 'partial_guidance', graph)
        or stop_event.set()
        or None,
    )
    monkeypatch.setattr(
        fuzzer,
        'berserker_fuzz',
        lambda *_args, **_kwargs: pytest.fail(
            'berserker must not start after the global deadline'
        ),
    )
    monkeypatch.setattr(analyzer, 'begin_phase', lambda *_args: None)
    monkeypatch.setattr(analyzer, 'end_phase', lambda *_args: None)
    monkeypatch.setattr(
        analyzer,
        'record_generator_checkpoint',
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(analyzer, 'stop_reason', 'deadline', raising=False)
    monkeypatch.setattr(analyzer, 'start_time', started, raising=False)

    fuzzer.state_fuzz(stop_event)

    assert fuzzer.partial_guidance is graph
    assert stop_event.is_set()
    assert analyzer.start_time == started
