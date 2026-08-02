import hashlib
import multiprocessing as mp
import threading
from types import SimpleNamespace

from voltron.executor.executor import Executor
from voltron.executor.mapper import Mapper


def test_missing_mutator_falls_back_to_generator(monkeypatch):
    mapper = Mapper.__new__(Mapper)
    mapper.mutators = {}
    mapper.message_pool = {}
    monkeypatch.setattr(
        mapper,
        'select_generators',
        lambda req_seq, **_kwargs: [(req_seq[0], b'BASELINE')],
    )

    assert mapper.select_mutators(['PING']) == [('PING', b'BASELINE')]


def test_failed_mutator_falls_back_to_generator(monkeypatch):
    mapper = Mapper.__new__(Mapper)
    mapper.mutators = {'PING': [SimpleNamespace(msg_type='PING', name='id0')]}
    mapper.message_pool = {}
    mapper.exec_retry_limit = 2
    monkeypatch.setattr(mapper, 'select_mutator', lambda *_args: mapper.mutators['PING'][0])
    monkeypatch.setattr(mapper, 'exe_mutator', lambda _mutator: None)
    monkeypatch.setattr(
        mapper,
        'select_generators',
        lambda req_seq, **_kwargs: [(req_seq[0], b'BASELINE')],
    )

    assert mapper.select_mutators(['PING']) == [('PING', b'BASELINE')]


def test_observer_runtime_is_isolated_and_falls_back_on_timeout():
    mapper = Mapper.__new__(Mapper)
    mapper.exec_timeout_s = 0.1
    mapper._dynamic_ctx = mp.get_context('spawn')
    mapper._dynamic_conn = None
    mapper._dynamic_proc = None
    mapper._dynamic_lock = threading.Lock()
    executor = Executor.__new__(Executor)
    executor.mapper = mapper
    executor.observer_funcs = {}
    executor.observer_sources = {
        '200': (
            'def packet_observer(response):\n'
            '    while True:\n'
            '        pass\n',
            'packet_observer',
        )
    }
    response = b'200 OK\r\n'
    try:
        assert executor.observe_response('200', response) == hashlib.sha256(
            response
        ).hexdigest()
    finally:
        mapper.close()
