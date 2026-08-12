import base64
import hashlib
import json
import threading

from voltron.executor.conversation import Conversation
from voltron.executor.pair_recorder import RequestResponsePairRecorder


def add_exchange(
    conversation: Conversation,
    request_type: str,
    response_type: str,
    request: bytes,
    response: bytes,
) -> None:
    conversation.add_state(request_type, response_type)
    conversation.add_data(request, response)


def test_records_first_relation_from_any_phase(tmp_path):
    recorder = RequestResponsePairRecorder(tmp_path)
    conversation = Conversation()
    conversation.add_state('-', '220')
    conversation.add_data(b'', b'welcome')
    add_exchange(conversation, 'USER', '331', b'USER test\r\n', b'331 pass\r\n')
    add_exchange(conversation, 'USER', '331', b'USER other\r\n', b'331 pass\r\n')
    add_exchange(conversation, 'PASS', '230', b'PASS secret\r\n', b'230 ok\r\n')

    assert recorder.observe(conversation, phase='model_learning') == 2
    files = sorted((tmp_path / 'request_response_pairs').glob('pair_*.json'))
    assert [path.name for path in files] == ['pair_000000.json', 'pair_000001.json']
    first = json.loads(files[0].read_text(encoding='utf-8'))
    assert first['phase'] == 'model_learning'
    assert base64.b64decode(first['request']['data']) == b'USER test\r\n'
    assert base64.b64decode(first['response']['data']) == b'331 pass\r\n'


def test_skips_abnormal_empty_and_incomplete_exchanges(tmp_path):
    recorder = RequestResponsePairRecorder(tmp_path)
    conversation = Conversation()
    add_exchange(conversation, 'USER', '331', b'', b'331 pass\r\n')
    add_exchange(conversation, 'USER', 'TIMEOUT', b'USER test\r\n', b'')
    conversation.req_seq.append('PASS')
    conversation.res_seq.append('230')

    assert recorder.observe(conversation, phase='fuzzing') == 0
    assert not (tmp_path / 'request_response_pairs').exists()


def test_concurrent_observation_writes_one_relation(tmp_path):
    recorder = RequestResponsePairRecorder(tmp_path)
    conversation = Conversation()
    add_exchange(conversation, 'USER', '331', b'USER test\r\n', b'331 pass\r\n')
    threads = [
        threading.Thread(target=recorder.observe, args=(conversation, 'fuzzing'))
        for _ in range(8)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    files = list((tmp_path / 'request_response_pairs').glob('pair_*.json'))
    assert len(files) == 1


def test_uses_next_available_file_id(tmp_path):
    target = tmp_path / 'request_response_pairs'
    target.mkdir()
    (target / 'pair_000000.json').write_text('{}', encoding='utf-8')
    recorder = RequestResponsePairRecorder(tmp_path)
    conversation = Conversation()
    add_exchange(conversation, 'USER', '331', b'USER test\r\n', b'331 pass\r\n')

    assert recorder.observe(conversation, phase='fuzzing') == 1
    assert (target / 'pair_000001.json').is_file()


def test_persists_runtime_component_provenance(tmp_path):
    recorder = RequestResponsePairRecorder(tmp_path)
    conversation = Conversation()
    add_exchange(conversation, 'PING', '200', b'PING', b'200 OK')
    raw_hash = hashlib.sha256(b'200 OK').hexdigest()
    runtime_components = {
        'checker': {
            'status': 'compliant',
            'scope': 'exact',
            'component_type': '200',
            'error': '',
        },
        'observer': {
            'semantic_fingerprint': 'a' * 64,
            'raw_fingerprint': raw_hash,
            'scope': 'exact',
            'component_type': '200',
            'provisional': False,
            'error': '',
        },
    }

    assert recorder.observe(
        conversation,
        phase='fuzzing',
        component_evidence={
            ('PING', '200', raw_hash): runtime_components,
        },
    ) == 1

    record = json.loads(next(
        (tmp_path / 'request_response_pairs').glob('pair_*.json')
    ).read_text(encoding='utf-8'))
    assert record['runtime_components'] == runtime_components


def test_persists_raw_batch_frame_metadata(tmp_path):
    recorder = RequestResponsePairRecorder(tmp_path)
    conversation = Conversation()
    conversation.add_state('RETR', '226')
    batch = b'150 opening\r\n226 done\r\n'
    conversation.add_data(
        b'RETR file\r\n', batch,
        response_frames=[
            {
                'recv_batch_id': 7, 'frame_index': 0,
                'offset_start': 0, 'offset_end': 13,
                'response_type': '150', 'parse_status': 'parsed',
            },
            {
                'recv_batch_id': 7, 'frame_index': 1,
                'offset_start': 13, 'offset_end': len(batch),
                'response_type': '226', 'parse_status': 'parsed',
            },
        ],
    )

    assert recorder.observe(conversation, phase='fuzzing') == 1
    record = json.loads(next(
        (tmp_path / 'request_response_pairs').glob('pair_*.json')
    ).read_text(encoding='utf-8'))
    assert record['response_length'] == len(batch)
    assert [frame['response_type'] for frame in record['response_frames']] == [
        '150', '226',
    ]
