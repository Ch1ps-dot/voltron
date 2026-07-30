import asyncio
from types import SimpleNamespace

from lxml import etree

from voltron.configs import configs
from voltron.synthesizer.generator import Generator
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
            self.calls = 0

        async def llm_mutator_evolve(self, **_kwargs):
            self.calls += 1
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
    assert chater.calls == 3


def test_invalid_checker_and_observer_are_retried_three_times_then_skipped(
    monkeypatch,
):
    _set_retry_limit(monkeypatch)

    class FailingChater:
        def __init__(self):
            self.checker_calls = 0
            self.observer_calls = 0

        async def llm_checker_gen(self, **_kwargs):
            self.checker_calls += 1
            return "def packet_checker(:\n"

        async def llm_observer_gen(self, **_kwargs):
            self.observer_calls += 1
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
    assert observer is None
    assert chater.checker_calls == 3
    assert chater.observer_calls == 3
