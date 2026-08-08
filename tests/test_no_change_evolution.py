import asyncio
from types import SimpleNamespace

from voltron.fuzz import Fuzzer
from voltron.llm.incremental import SourceDeltaResult
from voltron.synthesizer.generator import Generator
from voltron.synthesizer.parser import Parser
from voltron.synthesizer.synthesizer import AsyncProducer


def test_no_change_generator_result_does_not_publish_a_new_version(tmp_path):
    source = "def generate():\n    return b'PING\\r\\n'\n"
    generator_dir = tmp_path / "generators" / "PING"
    generator_dir.mkdir(parents=True)
    baseline_path = generator_dir / "id0.py"
    baseline_path.write_text(source, encoding="utf-8")

    producer = AsyncProducer.__new__(AsyncProducer)
    producer.generator_path = tmp_path / "generators"
    producer.generator_info_path = tmp_path / "generators" / "generator_info.json"
    producer.generators = {
        "PING": [Generator(
            msg_type="PING",
            name="id0",
            evolved_from="",
            path=str(baseline_path),
        )]
    }

    result = SourceDeltaResult(
        source,
        changed=False,
        reason="already_satisfies_goal",
    )

    assert producer._save_evolved_generators([("PING", result)]) == []
    assert [item.name for item in producer.generators["PING"]] == ["id0"]
    assert not (generator_dir / "id1.py").exists()
    assert producer._last_generator_evolution_outcome == {
        "attempted": 1,
        "changed": 0,
        "no_change": 1,
        "failed": 0,
    }


def test_threshold_relearning_accepts_explicit_generator_no_change():
    class Producer:
        _last_generator_evolution_outcome = {
            "attempted": 1,
            "changed": 0,
            "no_change": 1,
            "failed": 0,
        }

        def generator_evo(self, _hypothesis):
            return []

    fuzzer = Fuzzer.__new__(Fuzzer)
    fuzzer.spec_knowledge = True
    fuzzer.producer = Producer()

    assert fuzzer._evolve_after_learning_threshold(
        object(),
        object(),
    ) == []


def test_threshold_relearning_still_rejects_failed_generator_evolution():
    class Producer:
        _last_generator_evolution_outcome = {
            "attempted": 1,
            "changed": 0,
            "no_change": 0,
            "failed": 1,
        }

        def generator_evo(self, _hypothesis):
            return []

    fuzzer = Fuzzer.__new__(Fuzzer)
    fuzzer.spec_knowledge = True
    fuzzer.producer = Producer()

    try:
        fuzzer._evolve_after_learning_threshold(object(), object())
    except RuntimeError as error:
        assert "no usable generator versions" in str(error)
    else:
        raise AssertionError("failed generator evolution must remain fatal")


def test_parser_no_change_that_still_fails_the_real_sample_is_unresolved(tmp_path):
    source = "def packet_parser(response: bytes) -> bytes:\n    return b''\n"
    (tmp_path / "id0.py").write_text(source, encoding="utf-8")
    records = []

    class NoChangeChater:
        async def llm_parser_evolve(self, *, old_code, **_kwargs):
            return SourceDeltaResult(
                old_code,
                changed=False,
                reason="insufficient_evidence",
            )

    producer = AsyncProducer.__new__(AsyncProducer)
    producer.chater = NoChangeChater()
    producer.rfcp = SimpleNamespace(pro_name="demo")
    producer.parsers = [Parser(evolved_from="", name="id0", state_field="Code")]
    producer.parser_path = tmp_path
    producer._primary_response_field_info = lambda: "[]"
    producer._response_type_rules_info = lambda: "{}"
    producer._primary_response_field_name = lambda: "Code"

    async def no_ir_evolution(*_args, **_kwargs):
        return None

    producer._maybe_evolve_response_ir = no_ir_evolution
    producer._record_generation = lambda *args, **kwargs: records.append(
        (args, kwargs)
    )

    result = asyncio.run(producer._parser_evo_one(b"200 OK\r\n"))

    assert result is None
    assert records[0][0][2] == "no_change_unresolved"
    assert records[0][1]["changed"] is False
    assert records[0][1]["reason"] == "insufficient_evidence"


def test_observer_no_change_is_recorded_only_when_samples_already_converge():
    source = (
        "import hashlib\n\n"
        "def packet_observer(response: bytes) -> str:\n"
        "    return hashlib.sha256(response if isinstance(response, bytes) else b'').hexdigest()\n"
    )
    records = []

    class NoChangeChater:
        async def llm_observer_evolve(self, *, original_code, **_kwargs):
            return SourceDeltaResult(
                original_code,
                changed=False,
                reason="already_satisfies_goal",
            )

    producer = AsyncProducer.__new__(AsyncProducer)
    producer.chater = NoChangeChater()
    producer.rfcp = SimpleNamespace(pro_name="demo")
    producer._record_generation = lambda *args, **kwargs: records.append(
        (args, kwargs)
    )

    result = asyncio.run(producer._observer_evolve_async(
        "200",
        "<message />",
        source,
        [b"same", b"same"],
    ))

    assert result is None
    assert records[0][0][2] == "no_change"
    assert records[0][1]["changed"] is False


def test_checker_no_change_that_still_rejects_the_reviewed_response_is_unresolved():
    source = "def packet_checker(response: bytes) -> bool:\n    return False\n"
    records = []

    class NoChangeChater:
        async def llm_checker_evolve(self, *, original_code, **_kwargs):
            return SourceDeltaResult(
                original_code,
                changed=False,
                reason="no_safe_change",
            )

    producer = AsyncProducer.__new__(AsyncProducer)
    producer.chater = NoChangeChater()
    producer.rfcp = SimpleNamespace(pro_name="demo")
    producer._record_generation = lambda *args, **kwargs: records.append(
        (args, kwargs)
    )

    result = asyncio.run(producer._checker_evolve_async(
        "200",
        source,
        b"200 OK\r\n",
        {"summary": "allowed"},
    ))

    assert result is None
    assert records[0][0][2] == "no_change_unresolved"
    assert records[0][1]["changed"] is False
