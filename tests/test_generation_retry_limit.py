import asyncio
import hashlib
import json
from types import SimpleNamespace

import pytest

from voltron.analyzer.analyzer import analyzer
from lxml import etree

from voltron.configs import configs
from voltron.llm.chatter import AsyncChater
from voltron.synthesizer.generator import Generator
from voltron.synthesizer.code_validation import RAW_SHA256_OBSERVER
from voltron.synthesizer.synthesizer import AsyncProducer


def _set_retry_limit(monkeypatch) -> None:
    monkeypatch.setattr(configs, "generation_retry_limit", 3, raising=False)


def test_initial_generator_failure_isolated_to_its_request_type(
    tmp_path,
    monkeypatch,
):
    _set_retry_limit(monkeypatch)
    monkeypatch.setattr(configs, "async_sem_fuzz", 2, raising=False)
    info_path = tmp_path / "info.md"
    info_path.write_text("target info", encoding="utf-8")

    class MixedChater:
        async def llm_generator_gen(self, *, msg_type, **_kwargs):
            if msg_type == "GOOD":
                return "def generate():\n    return b'PING\\r\\n'\n"
            return "def generate(:\n"

        async def llm_code_repair(self, **_kwargs):
            return "def generate(:\n"

    producer = AsyncProducer.__new__(AsyncProducer)
    producer.chater = MixedChater()
    producer.rfcp = SimpleNamespace(
        pro_name="example",
        req_fields=["method"],
        req_types={"GOOD", "BAD"},
        req_dep_map={"GOOD": {}, "BAD": {"GOOD": {"kind": "after"}}},
        poss_res={"GOOD": ["OK"], "BAD": ["ERR"]},
    )
    producer.req_ir = etree.fromstring(
        b"<ir><message name='GOOD'/><message name='BAD'/></ir>"
    )
    producer.generator_path = tmp_path / "generators"
    producer.generator_path.mkdir()
    producer.generator_info_path = producer.generator_path / "generator_info.json"
    producer.info_path = info_path
    producer.req_types = {"GOOD", "BAD"}
    producer.req_dep = dict(producer.rfcp.req_dep_map)
    producer.poss_response = dict(producer.rfcp.poss_res)
    producer.generators = {}
    producer._record_generation = lambda *_args, **_kwargs: None
    producer._generated_code_timeout = lambda: 1
    producer._generated_message_limit = lambda: 4096
    producer._request_type_rule_info = lambda _msg_type: "rule"

    producer.generator_gen()

    assert set(producer.generators) == {"GOOD"}
    assert producer.req_types == {"GOOD"}
    assert producer.req_dep == {"GOOD": {}}
    assert producer.poss_response == {"GOOD": ["OK"]}
    assert (producer.generator_path / "GOOD" / "id0.py").is_file()
    assert not (producer.generator_path / "BAD" / "id0.py").exists()
    assert set(json.loads(producer.generator_info_path.read_text())) == {"GOOD"}


def test_initial_generator_all_failures_remain_fatal(tmp_path, monkeypatch):
    _set_retry_limit(monkeypatch)
    monkeypatch.setattr(configs, "async_sem_fuzz", 1, raising=False)
    info_path = tmp_path / "info.md"
    info_path.write_text("target info", encoding="utf-8")

    class FailingChater:
        async def llm_generator_gen(self, **_kwargs):
            return "def generate(:\n"

        async def llm_code_repair(self, **_kwargs):
            return "def generate(:\n"

    producer = AsyncProducer.__new__(AsyncProducer)
    producer.chater = FailingChater()
    producer.rfcp = SimpleNamespace(
        pro_name="example",
        req_fields=["method"],
        req_types={"BAD"},
        req_dep_map={"BAD": {}},
        poss_res={"BAD": []},
    )
    producer.req_ir = etree.fromstring(b"<ir><message name='BAD'/></ir>")
    producer.generator_path = tmp_path / "generators"
    producer.generator_path.mkdir()
    producer.generator_info_path = producer.generator_path / "generator_info.json"
    producer.info_path = info_path
    producer.req_types = {"BAD"}
    producer.req_dep = {"BAD": {}}
    producer.poss_response = {"BAD": []}
    producer.generators = {}
    producer._record_generation = lambda *_args, **_kwargs: None
    producer._generated_code_timeout = lambda: 1
    producer._generated_message_limit = lambda: 4096
    producer._request_type_rule_info = lambda _msg_type: "rule"

    with pytest.raises(RuntimeError, match="no usable request types"):
        producer.generator_gen()
    assert not producer.generator_info_path.exists()


def test_invalid_mutator_is_retried_three_times_then_skipped(tmp_path, monkeypatch):
    _set_retry_limit(monkeypatch)
    generator_path = tmp_path / "generator.py"
    generator_path.write_text(
        "def generate():\n    return b'PING\\r\\n'\n",
        encoding="utf-8",
    )

    class FailingChater:
        def __init__(self):
            self.generate_calls = 0
            self.repair_calls = 0

        async def llm_mutator_evolve(self, **_kwargs):
            self.generate_calls += 1
            return "def mutate(:\n"

        async def llm_code_repair(self, **_kwargs):
            self.repair_calls += 1
            return "def mutate(:\n"

    chater = FailingChater()
    producer = AsyncProducer.__new__(AsyncProducer)
    producer.generators = {
        "PING": [
            Generator(
                msg_type="PING",
                name="id0",
                evolved_from="",
                path=str(generator_path),
            )
        ]
    }
    producer.best_generators = {}
    producer.chater = chater
    producer.rfcp = SimpleNamespace(pro_name="example", req_fields=["method"])
    producer.poss_response = {"PING": []}
    producer._request_ir_info = lambda _msg_type: "<message />"

    result = asyncio.run(
        producer._generator_mutate_one(
            "PING", "SUT information", {"PING": set()}, asyncio.Semaphore(1)
        )
    )

    assert result is None
    assert chater.generate_calls == 1
    assert chater.repair_calls == 2


def test_mutator_delta_missing_entry_is_repaired_from_candidate(
    tmp_path,
    monkeypatch,
):
    _set_retry_limit(monkeypatch)
    generator_path = tmp_path / "generator.py"
    baseline = "def generate():\n    return b'PING\\r\\n'\n"
    generator_path.write_text(baseline, encoding="utf-8")

    class DeltaThenRepairChater:
        def __init__(self):
            self.evolve_calls = 0
            self.repair_kwargs = None

        async def llm_mutator_evolve(self, *, code, **_kwargs):
            self.evolve_calls += 1
            delta = json.dumps({
                "base_sha256": hashlib.sha256(code.encode()).hexdigest(),
                "edits": [{
                    "start_line": 1,
                    "end_line": 2,
                    "replacement": "def generate():\n    return b'BROKEN\\r\\n'",
                }],
            })
            return AsyncChater._apply_python_delta(code, delta, "mutate")

        async def llm_code_repair(self, **kwargs):
            self.repair_kwargs = kwargs
            return "def mutate():\n    return b'MUTATED\\r\\n'\n"

    chater = DeltaThenRepairChater()
    producer = AsyncProducer.__new__(AsyncProducer)
    producer.generators = {
        "PING": [
            Generator(
                msg_type="PING",
                name="id0",
                evolved_from="",
                path=str(generator_path),
            )
        ]
    }
    producer.best_generators = {}
    producer.chater = chater
    producer.rfcp = SimpleNamespace(pro_name="example", req_fields=["method"])
    producer.poss_response = {"PING": []}
    producer._request_ir_info = lambda _msg_type: "<message />"
    producer._record_generation = lambda *_args, **_kwargs: None

    result = asyncio.run(
        producer._generator_mutate_one(
            "PING", "SUT information", {"PING": set()}, asyncio.Semaphore(1)
        )
    )

    assert result == ("PING", "def mutate():\n    return b'MUTATED\\r\\n'\n")
    assert chater.evolve_calls == 1
    assert chater.repair_kwargs["code"] == (
        "def generate():\n    return b'BROKEN\\r\\n'\n"
    )
    assert "missing_function: mutate" in chater.repair_kwargs["error"]
    assert chater.repair_kwargs["function_name"] == "mutate"


def test_invalid_checker_and_observer_are_retried_three_times_then_skipped(
    monkeypatch,
):
    _set_retry_limit(monkeypatch)

    class FailingChater:
        def __init__(self):
            self.checker_calls = 0
            self.observer_calls = 0
            self.repair_calls = 0

        async def llm_checker_gen(self, **_kwargs):
            self.checker_calls += 1
            return "def packet_checker(:\n"

        async def llm_observer_gen(self, **_kwargs):
            self.observer_calls += 1
            return "def packet_observer(:\n"

        async def llm_code_repair(self, **_kwargs):
            self.repair_calls += 1
            return "def packet_observer(:\n"

    chater = FailingChater()
    producer = AsyncProducer.__new__(AsyncProducer)
    producer.chater = chater
    producer.rfcp = SimpleNamespace(pro_name="example")
    producer._response_type_rule_info = lambda _response_type: "rules"
    response_message = etree.Element("message", name="response")

    checker = asyncio.run(
        producer._checker_gen_one(
            "OK", response_message, "response fields", asyncio.Semaphore(1)
        )
    )
    observer = asyncio.run(
        producer._observer_gen_one(
            "OK", response_message, "response fields", asyncio.Semaphore(1)
        )
    )

    assert checker is None
    assert observer == ("OK", RAW_SHA256_OBSERVER)
    assert chater.checker_calls == 3
    assert chater.observer_calls == 1
    assert chater.repair_calls == 2


def test_generator_evolution_retries_after_invalid_generated_code(
    tmp_path,
    monkeypatch,
):
    generator_path = tmp_path / "generators" / "PING"
    generator_path.mkdir(parents=True)
    (generator_path / "id0.py").write_text(
        "def generate():\n    return b'PING\\r\\n'\n",
        encoding="utf-8",
    )

    class RetryingChater:
        def __init__(self):
            self.generate_calls = 0
            self.repair_kwargs = None

        async def llm_generator_evolve(self, **_kwargs):
            self.generate_calls += 1
            return "def generate():\n    raise RuntimeError('generation failed')\n"

        async def llm_code_repair(self, **kwargs):
            self.repair_kwargs = kwargs
            return "def generate():\n    return b'PING\\r\\n'\n"

    chater = RetryingChater()
    producer = AsyncProducer.__new__(AsyncProducer)
    producer.chater = chater
    producer.rfcp = SimpleNamespace(pro_name="example", req_fields=["method"])
    producer.generator_path = tmp_path / "generators"
    producer.generators = {
        "PING": [
            Generator(
                msg_type="PING",
                name="id0",
                evolved_from="init",
                path=str(tmp_path / "stale-generator-metadata.py"),
            )
        ]
    }
    producer.req_dep = {}
    producer._request_ir_info = lambda _msg_type: "<message />"
    producer._maybe_evolve_request_ir = lambda *_args: None
    monkeypatch.setattr(
        configs,
        "ir_evolution_failure_threshold",
        3,
        raising=False,
    )
    monkeypatch.setattr(analyzer, "finished", 0, raising=False)

    result = asyncio.run(
        producer._generator_evo_one(
            "PING",
            "SUT information",
            SimpleNamespace(id=0, get_relation=lambda *_args: ""),
            asyncio.Semaphore(1),
        )
    )

    assert result == ("PING", "def generate():\n    return b'PING\\r\\n'\n")
    assert chater.generate_calls == 1
    assert "RuntimeError('generation failed')" in chater.repair_kwargs["code"]
    assert "RuntimeError: generation failed" in chater.repair_kwargs["error"]
    assert chater.repair_kwargs["function_name"] == "generate"


def test_generator_evolution_skips_a_missing_baseline(tmp_path):
    class UnexpectedChater:
        async def llm_generator_evolve(self, **_kwargs):
            raise AssertionError("LLM must not be called without a baseline")

    producer = AsyncProducer.__new__(AsyncProducer)
    producer.chater = UnexpectedChater()
    producer.generators = {}
    producer.generator_path = tmp_path / "generators"
    producer.req_dep = {}

    result = asyncio.run(
        producer._generator_evo_one(
            "MISSING",
            "SUT information",
            SimpleNamespace(id=9, get_relation=lambda *_args: ""),
            asyncio.Semaphore(1),
        )
    )

    assert result is None


def test_generator_evolution_stops_after_retry_limit(tmp_path, monkeypatch):
    generator_path = tmp_path / "generators" / "PING"
    generator_path.mkdir(parents=True)
    baseline_path = generator_path / "id0.py"
    baseline_path.write_text(
        "def generate():\n    return b'PING\\r\\n'\n",
        encoding="utf-8",
    )

    class FailingChater:
        def __init__(self):
            self.calls = 0

        async def llm_generator_evolve(self, **_kwargs):
            self.calls += 1
            return "def generate(:\n"

        async def llm_code_repair(self, **_kwargs):
            self.calls += 1
            return "def generate(:\n"

    chater = FailingChater()
    producer = AsyncProducer.__new__(AsyncProducer)
    producer.chater = chater
    producer.rfcp = SimpleNamespace(pro_name="example", req_fields=["method"])
    producer.generator_path = tmp_path / "generators"
    producer.generators = {
        "PING": [
            Generator(
                msg_type="PING",
                name="id0",
                evolved_from="init",
                path=str(baseline_path),
            )
        ]
    }
    producer.req_dep = {}
    producer._request_ir_info = lambda _msg_type: "<message />"

    async def no_ir_evolution(*_args):
        return False

    producer._maybe_evolve_request_ir = no_ir_evolution
    monkeypatch.setattr(configs, "generation_retry_limit", 3, raising=False)
    monkeypatch.setattr(
        configs,
        "ir_evolution_failure_threshold",
        99,
        raising=False,
    )

    result = asyncio.run(
        producer._generator_evo_one(
            "PING",
            "SUT information",
            SimpleNamespace(id=0, get_relation=lambda *_args: ""),
            asyncio.Semaphore(1),
        )
    )

    assert result is None
    assert chater.calls == 3


def test_parser_generation_repairs_invalid_generated_code():
    class RetryingChater:
        def __init__(self):
            self.parser_calls = 0
            self.repair_kwargs = None

        async def llm_parser_gen(self, **_kwargs):
            self.parser_calls += 1
            return "def packet_parser(:\n"

        async def llm_code_repair(self, **kwargs):
            self.repair_kwargs = kwargs
            return "def packet_parser(_response):\n    return b'OK'\n"

    chater = RetryingChater()
    producer = AsyncProducer.__new__(AsyncProducer)
    producer.chater = chater
    producer.rfcp = SimpleNamespace(pro_name="example")
    producer._primary_response_field_info = lambda: "response fields"
    producer._response_type_rules_info = lambda: "rules"

    result = asyncio.run(producer._parser_gen_async())

    assert result == "def packet_parser(_response):\n    return b'OK'\n"
    assert chater.parser_calls == 1
    assert chater.repair_kwargs["code"] == "def packet_parser(:\n"
    assert "SyntaxError" in chater.repair_kwargs["error"]
    assert chater.repair_kwargs["function_name"] == "packet_parser"
