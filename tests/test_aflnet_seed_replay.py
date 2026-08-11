import threading

from voltron.aflnet_seeds import AFLNetSeed
from voltron.configs import configs
from voltron.fuzz import Fuzzer
import voltron.fuzz as fuzz_module
from voltron.scheduler.berserker import Berserker


class AnalyzerStub:
    def __init__(self):
        self.events = []

    def begin_phase(self, phase):
        self.events.append(('begin', phase))

    def end_phase(self, phase, status):
        self.events.append(('end', phase, status))

    def record_skipped_phase(self, phase):
        self.events.append(('skipped', phase))

    def phase_stop_status(self):
        return 'stopped'


def test_loader_exposes_raw_seed_messages_without_mapper(monkeypatch):
    seeds = (AFLNetSeed('seed_1', (b'USER a\r\n', b'PASS b\r\n')),)
    monkeypatch.setattr(fuzz_module, 'load_aflnet_seeds', lambda *_args: seeds)
    analyzer = AnalyzerStub()
    monkeypatch.setattr(fuzz_module, 'analyzer', analyzer)
    monkeypatch.setattr(configs, 'aflnet_seed_loading_enabled', True)
    monkeypatch.setattr(configs, 'base_path', __import__('pathlib').Path('.'))
    monkeypatch.setattr(configs, 'pro_name', 'ftp', raising=False)

    fuzzer = Fuzzer.__new__(Fuzzer)
    fuzzer.target_name = 'bftpd'

    sequences = fuzzer.load_aflnet_seed_sequences()

    assert sequences == [[
        ('aflnet-seed:seed_1:0', b'USER a\r\n'),
        ('aflnet-seed:seed_1:1', b'PASS b\r\n'),
    ]]
    assert analyzer.events == [
        ('begin', 'aflnet_seed_loading'),
        ('end', 'aflnet_seed_loading', 'completed'),
    ]


def test_loading_is_skipped_by_default(monkeypatch):
    analyzer = AnalyzerStub()
    monkeypatch.setattr(fuzz_module, 'analyzer', analyzer)
    monkeypatch.setattr(configs, 'aflnet_seed_loading_enabled', False)
    fuzzer = Fuzzer.__new__(Fuzzer)

    assert fuzzer.load_aflnet_seed_sequences() == []

    assert analyzer.events == [('skipped', 'aflnet_seed_loading')]


def test_imported_seed_is_a_concrete_interesting_prefix():
    class Mapper:
        request_types = {'GENERATED'}
        req_dep = {}

    imported = [('aflnet-seed:seed_1:0', b'USER a\r\n')]
    berserker = Berserker(
        Mapper(),
        object(),
        None,
        interesting_seed_sequences=[imported],
    )

    class RandomStub:
        @staticmethod
        def random():
            return 0.0

        @staticmethod
        def choice(values):
            return values[0]

    berserker.rand = RandomStub()
    assert imported in berserker.useful_seq
    assert berserker.select_base_state() == imported
    assert berserker.selected_imported_seed_prefix is True
    assert berserker.selected_partial_prefix is False
