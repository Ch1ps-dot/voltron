from pathlib import Path

from voltron.configs import configs
from voltron.synthesizer.synthesizer import AsyncProducer, Generator, Parser


def test_no_spec_run_generates_fresh_components_without_loading_cache(
    tmp_path: Path,
    monkeypatch,
):
    calls = []
    producer = AsyncProducer.__new__(AsyncProducer)
    producer.generator_info_path = tmp_path / "cached-generators.json"
    producer.parser_info_path = tmp_path / "cached-parser.json"
    producer.mutator_info_path = tmp_path / "mutator_info.json"
    producer.generators = {}
    producer.parsers = []
    producer.checkers = {}
    producer.observers = {}
    producer.mutators = {
        "OLD": [Generator(name="id0", msg_type="OLD", evolved_from="init", path="")]
    }
    producer.best_generators = {}
    producer.best_parser_info = {}

    def generator_gen():
        calls.append("generator")
        producer.generators = {
            "NEW": [Generator(
                name="id0", msg_type="NEW", evolved_from="init", path="",
            )]
        }

    def parser_gen():
        calls.append("parser")
        producer.parsers = [Parser(name="id0", evolved_from="init")]

    producer.generator_gen = generator_gen
    producer.parser_gen = parser_gen
    producer.load_best_equipment = lambda: (_ for _ in ()).throw(
        AssertionError("must not read full-run best equipment")
    )
    monkeypatch.setattr(configs, "spec_knowledge", False, raising=False)
    monkeypatch.setattr(configs, "fuzz_mode", "fuzz", raising=False)
    monkeypatch.setattr(configs, "compliance_analysis", False, raising=False)

    producer.run()

    assert calls == ["generator", "parser"]
    assert set(producer.generators) == {"NEW"}
    assert producer.mutators == {}
