import asyncio
from types import SimpleNamespace

from voltron.analyzer.analyzer import analyzer
from lxml import etree

from voltron.configs import configs
from voltron.synthesizer.generator import Generator
from voltron.synthesizer.code_validation import RAW_SHA256_OBSERVER
from voltron.synthesizer.synthesizer import AsyncProducer


def _set_retry_limit(monkeypatch) -> None:
    monkeypatch.setattr(configs, "generation_retry_limit", 3, raising=False)


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
