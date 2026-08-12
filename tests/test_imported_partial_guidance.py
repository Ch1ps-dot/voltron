import pickle
from pathlib import Path
from types import SimpleNamespace

from voltron.configs import configs
from voltron.fuzz import Fuzzer
from voltron.learner.partial_guidance import PartialStateGraph, PartialTrace
from voltron.synthesizer.synthesizer import AsyncProducer


def _graph(target: str = 'demo') -> PartialStateGraph:
    return PartialStateGraph(
        fingerprint={
            'target': target,
            'protocol': 'demo-proto',
            'endpoint': '127.0.0.1:1',
            'parser': 'parser-v1',
            'generators': {'PING': 'generator-v1'},
        },
        traces=[
            PartialTrace(
                messages=(('PING', b'PING\r\n'),),
                responses=('PONG',),
            )
        ],
    )


def _fuzzer(tmp_path: Path, monkeypatch) -> Fuzzer:
    monkeypatch.setattr(configs, 'models_path', tmp_path, raising=False)
    monkeypatch.setattr(configs, 'target_name', 'demo', raising=False)
    monkeypatch.setattr(configs, 'pro_name', 'demo-proto', raising=False)
    monkeypatch.setattr(configs, 'host', '127.0.0.1', raising=False)
    monkeypatch.setattr(configs, 'port', 1, raising=False)
    monkeypatch.setattr(
        configs, 'reuse_imported_partial_guidance', True, raising=False
    )
    fuzzer = Fuzzer.__new__(Fuzzer)
    fuzzer.target_name = 'demo'
    fuzzer.mapper = SimpleNamespace(
        cur_parser=SimpleNamespace(name='parser-v1'),
        generators={'PING': [SimpleNamespace(name='generator-v1')]},
    )
    return fuzzer


def test_load_imported_partial_guidance_requires_matching_fingerprint(
    tmp_path, monkeypatch
):
    fuzzer = _fuzzer(tmp_path, monkeypatch)
    with (tmp_path / 'partial_guidance.pkl').open('wb') as stream:
        pickle.dump(_graph(), stream)

    loaded = fuzzer._load_imported_partial_guidance()

    assert loaded is not None
    assert loaded.seed_sequences() == [[('PING', b'PING\r\n')]]


def test_load_imported_partial_guidance_rejects_mismatched_equipment(
    tmp_path, monkeypatch
):
    fuzzer = _fuzzer(tmp_path, monkeypatch)
    with (tmp_path / 'partial_guidance.pkl').open('wb') as stream:
        pickle.dump(_graph(target='other-target'), stream)

    assert fuzzer._load_imported_partial_guidance() is None


def test_load_best_equipment_rebases_imported_absolute_paths(tmp_path):
    snapshot = tmp_path / 'best_equipment'
    generators = snapshot / 'generators'
    generators.mkdir(parents=True)
    (generators / 'PING.py').write_text('def generate(): pass\n')
    (snapshot / 'parser.py').write_text('def parse(): pass\n')
    manifest = {
        'model_id': '1',
        'generators': {
            'PING': {
                'msg_type': 'PING',
                'name': 'id0',
                'evolved_from': 'init',
                'path': '/remote/component/models/demo/best_equipment/generators/PING.py',
                'cur_res': [],
                'pre_res': [],
                'fut_res': [],
                'was_used': 0,
                'broken': False,
            }
        },
        'parser': {
            'name': 'id0',
            'evolved_from': 'init',
            'state_field': 'code',
            'parsed_res': [],
            'path': '/remote/component/models/demo/best_equipment/parser.py',
        },
    }
    (snapshot / 'best_equipment.json').write_text(__import__('json').dumps(manifest))
    producer = AsyncProducer.__new__(AsyncProducer)
    producer.best_equipment_path = snapshot
    producer.best_generator_path = generators
    producer.best_parser_path = snapshot / 'parser.py'
    producer.best_equipment_info_path = snapshot / 'best_equipment.json'

    producer.load_best_equipment()

    assert producer.best_generators['PING'].path == str(
        (generators / 'PING.py').resolve()
    )
    assert producer.best_parser_info['path'] == str(
        (snapshot / 'parser.py').resolve()
    )
