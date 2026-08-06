import asyncio
import json
from pathlib import Path
from string import Template
from types import SimpleNamespace

from voltron.llm.chatter import AsyncChater
from voltron.configs import configs
from voltron.synthesizer.generator import Generator
from voltron.synthesizer.synthesizer import AsyncProducer


def test_generator_mutation_serializes_observed_responses_deterministically(
    tmp_path,
):
    generator_path = tmp_path / "generator.py"
    generator_path.write_text(
        "def generate():\n    return b'LATEST\\r\\n'\n",
        encoding="utf-8",
    )
    best_generator_path = tmp_path / "best_generator.py"
    best_generator_path.write_text(
        "def generate():\n    return b'BEST\\r\\n'\n",
        encoding="utf-8",
    )
    captured = {}

    class FakeChater:
        async def llm_mutator_evolve(self, **kwargs):
            captured.update(kwargs)
            return "def mutate():\n    return b'MUTATED\\r\\n'\n"

    producer = AsyncProducer.__new__(AsyncProducer)
    producer.generators = {
        "PING": [
            Generator(
                msg_type="PING",
                evolved_from="",
                name="id0",
                path=str(generator_path),
            )
        ]
    }
    producer.best_generators = {
        "PING": Generator(
            msg_type="PING",
            evolved_from="id0",
            name="id1",
            path=str(best_generator_path),
        )
    }
    producer.chater = FakeChater()
    producer.rfcp = SimpleNamespace(
        pro_name="example",
        req_fields=["method"],
    )
    producer.poss_response = {"PING": ["PONG", "ERROR"]}
    producer._request_ir_info = lambda _msg_type: "<message />"

    result = asyncio.run(
        producer._generator_mutate_one(
            msg_type="PING",
            doc_info="SUT information",
            req_res={"PING": {"ERROR", "PONG"}},
            sem=asyncio.Semaphore(1),
        )
    )

    assert result[0] == "PING"
    assert json.loads(captured["trace"]) == ["ERROR", "PONG"]
    assert captured["trace"] == '["ERROR", "PONG"]'
    assert "return b'BEST" in captured["code"]
    assert "return b'LATEST" not in captured["code"]


def test_mutator_prompt_includes_runtime_response_feedback():
    prompt_path = (
        Path(__file__).resolve().parents[1]
        / "skills"
        / "evolver"
        / "generator_mutate.md"
    )
    chater = AsyncChater.__new__(AsyncChater)
    chater.pmp = SimpleNamespace(
        _tem_mutator_evolve=Template(
            prompt_path.read_text(encoding="utf-8")
        )
    )
    captured = {}

    async def fake_chat_llm(prompt, usage):
        captured["prompt"] = prompt
        captured["usage"] = usage
        return "def mutate():\n    return b'MUTATED\\r\\n'\n"

    chater.chat_llm = fake_chat_llm

    result = asyncio.run(
        chater.llm_mutator_evolve(
            pro_name="example",
            field_name="method",
            msg_type="PING",
            code="def generate():\n    return b'PING\\r\\n'\n",
            msg_ir="<message />",
            info="SUT information",
            poss_response="PONG\nERROR\nUNSUPPORTED",
            trace='["ERROR", "PONG"]',
        )
    )

    assert result == "def mutate():\n    return b'MUTATED\\r\\n'\n"
    assert captured["usage"] == "mutator_evolve"
    assert "Observed response types from the current fuzzing session" in (
        captured["prompt"]
    )
    assert "Saved Best Generator Program" in captured["prompt"]
    assert '["ERROR", "PONG"]' in captured["prompt"]
    assert "not yet been reached" in captured["prompt"]


def test_code_repair_prompt_includes_failed_code_and_validation_error():
    prompt_path = (
        Path(__file__).resolve().parents[1]
        / "skills"
        / "builder"
        / "code_repair.md"
    )
    chater = AsyncChater.__new__(AsyncChater)
    chater.pmp = SimpleNamespace(
        _tem_code_repair=Template(prompt_path.read_text(encoding="utf-8"))
    )
    captured = {}

    async def fake_chat_llm(prompt, usage):
        captured["prompt"] = prompt
        captured["usage"] = usage
        return "def generate():\n    return b'PING\\r\\n'\n"

    chater.chat_llm = fake_chat_llm

    result = asyncio.run(
        chater.llm_code_repair(
            code="def generate(:\n",
            error="SyntaxError: invalid syntax (<string>, line 1)",
            function_name="generate",
        )
    )

    assert result == "def generate():\n    return b'PING\\r\\n'\n"
    assert captured["usage"] == "code_repair"
    assert "def generate(:" in captured["prompt"]
    assert "SyntaxError: invalid syntax" in captured["prompt"]
    assert "function named `generate`" in captured["prompt"]


def test_code_repair_compacts_large_variable_context(monkeypatch):
    prompt_path = (
        Path(__file__).resolve().parents[1]
        / "skills"
        / "builder"
        / "code_repair.md"
    )
    chater = AsyncChater.__new__(AsyncChater)
    chater.pmp = SimpleNamespace(
        _tem_code_repair=Template(prompt_path.read_text(encoding="utf-8"))
    )
    captured = {}

    async def fake_chat_llm(prompt, usage):
        captured["prompt"] = prompt
        captured["usage"] = usage
        return "def generate():\n    return b'PING\\r\\n'\n"

    monkeypatch.setattr(configs, "prompt_context_max_chars", 512)
    chater.chat_llm = fake_chat_llm
    code = "CODE-START\n" + ("x" * 2_000) + "\nCODE-END"
    error = "ERROR-START\n" + ("y" * 2_000) + "\nERROR-END"

    asyncio.run(
        chater.llm_code_repair(
            code=code,
            error=error,
            function_name="generate",
        )
    )

    assert captured["usage"] == "code_repair"
    assert captured["prompt"].count("[... Voltron context truncated ...]") == 2
    for boundary in ("CODE-START", "CODE-END", "ERROR-START", "ERROR-END"):
        assert boundary in captured["prompt"]
