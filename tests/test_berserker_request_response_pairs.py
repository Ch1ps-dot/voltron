import base64
import json

from voltron.configs import configs
from voltron.executor.conversation import Conversation
from voltron.scheduler.berserker import Havoc


class DummyMapper:
    request_types = {'USER', 'PASS'}
    req_dep = {}
    mutators = {}


class DummyExecutor:
    def __init__(self) -> None:
        self.saved_conversations = []

    def save_cons(self, cons: Conversation) -> None:
        self.saved_conversations.append(cons)


def make_havoc() -> Havoc:
    return Havoc(
        mapper=DummyMapper(),
        exe=DummyExecutor(),
        machine=None,
    )


def add_exchange(
    cons: Conversation,
    request_type: str,
    response_type: str,
    request: bytes,
    response: bytes,
) -> None:
    cons.add_state(request_type, response_type)
    cons.add_data(request, response)


def test_saves_each_new_request_response_relation_once(tmp_path):
    configs.results_path = tmp_path
    havoc = make_havoc()
    cons = Conversation()
    cons.add_state('-', '220')
    cons.add_data(b'', b'welcome')
    add_exchange(cons, 'USER', '331', b'USER test\r\n', b'331 password\r\n')
    add_exchange(cons, 'USER', '331', b'USER other\r\n', b'331 password\r\n')
    add_exchange(cons, 'USER', '230', b'USER test\r\n', b'230 logged in\r\n')
    add_exchange(cons, 'PASS', '230', b'PASS secret\r\n', b'230 logged in\r\n')

    havoc.analyze_cons(cons, trans_inc=0, type_inc=0)

    pair_files = sorted(
        (tmp_path / 'request_response_pairs').glob('pair_*.json')
    )
    assert [path.name for path in pair_files] == [
        'pair_000000.json',
        'pair_000001.json',
        'pair_000002.json',
    ]

    first_pair = json.loads(pair_files[0].read_text(encoding='utf-8'))
    assert first_pair['request_type'] == 'USER'
    assert first_pair['response_type'] == '331'
    assert first_pair['request_length'] == len(b'USER test\r\n')
    assert first_pair['response_length'] == len(b'331 password\r\n')
    assert base64.b64decode(first_pair['request']['data']) == b'USER test\r\n'
    assert base64.b64decode(first_pair['response']['data']) == b'331 password\r\n'

    duplicate = Conversation()
    add_exchange(duplicate, 'USER', '331', b'USER third\r\n', b'331 password\r\n')
    havoc.analyze_cons(duplicate, trans_inc=0, type_inc=0)

    assert len(list(pair_files[0].parent.glob('pair_*.json'))) == 3


def test_skips_abnormal_empty_and_incomplete_exchanges(tmp_path):
    configs.results_path = tmp_path
    havoc = make_havoc()

    empty_request = Conversation()
    add_exchange(
        empty_request,
        'USER',
        '331',
        b'',
        b'331 password\r\n',
    )
    havoc.analyze_cons(empty_request, trans_inc=0, type_inc=0)

    incomplete = Conversation()
    incomplete.res_seq.append('230')
    havoc.analyze_cons(incomplete, trans_inc=0, type_inc=0)

    abnormal = Conversation()
    add_exchange(abnormal, 'USER', 'TIMEOUT', b'USER test\r\n', b'')
    havoc.analyze_cons(abnormal, trans_inc=0, type_inc=0)

    assert not (tmp_path / 'request_response_pairs').exists()


def test_uses_next_available_file_id(tmp_path):
    target_folder = tmp_path / 'request_response_pairs'
    target_folder.mkdir()
    (target_folder / 'pair_000000.json').write_text('{}', encoding='utf-8')
    configs.results_path = tmp_path
    havoc = make_havoc()
    cons = Conversation()
    add_exchange(cons, 'USER', '331', b'USER test\r\n', b'331 password\r\n')

    havoc.analyze_cons(cons, trans_inc=0, type_inc=0)

    assert (target_folder / 'pair_000001.json').is_file()
