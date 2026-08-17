from pathlib import Path

from voltron.configs import configs
from voltron.rfcparser.rfc_parser import AsyncRFCParser
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


def test_no_spec_bootstrap_catalog_round_trips_without_an_llm(tmp_path: Path):
    parser = AsyncRFCParser.__new__(AsyncRFCParser)
    parser.req_fields = ['command']
    parser.res_fields = ['status']
    parser.req_type_rules = {
        'types': [{'type_name': 'PING', 'field_values': {'command': 'PING'}}],
    }
    parser.res_type_rules = {
        'types': [{'type_name': 'OK', 'field_values': {'status': '200'}}],
    }
    parser.req_json = [{'field_name': 'command'}]
    parser.res_json = [{'field_name': 'status'}]

    metadata = tmp_path / 'no_spec_bootstrap.json'
    parser.save_no_spec_bootstrap(metadata)

    restored = AsyncRFCParser.__new__(AsyncRFCParser)
    restored.load_no_spec_bootstrap(metadata)

    assert restored.req_types == {'PING'}
    assert restored.res_types == {'OK'}
    assert restored.req_ir.findall('message')[0].get('name') == 'PING'
