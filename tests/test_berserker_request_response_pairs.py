from voltron.configs import configs
from voltron.executor.conversation import Conversation
from voltron.scheduler.berserker import Berserker


class DummyMapper:
    request_types = {'USER', 'PASS'}
    req_dep = {}
    mutators = {}


class DummyExecutor:
    def __init__(self) -> None:
        self.saved_conversations = []

    def save_cons(self, cons: Conversation) -> None:
        self.saved_conversations.append(cons)


def make_berserker() -> Berserker:
    return Berserker(
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


def test_new_request_response_relation_is_recorded_without_retaining_seed(tmp_path):
    configs.results_path = tmp_path
    berserker = make_berserker()
    berserker.unique_resp.add('331')
    berserker.max_seq_len = 1
    berserker.max_unique_resp_num = 1

    cons = Conversation()
    add_exchange(cons, 'USER', '331', b'USER test\r\n', b'331 password\r\n')

    berserker.analyze_cons(cons, trans_inc=0, type_inc=0)

    assert berserker.exe.saved_conversations == []
    assert berserker.req_res == {'USER': {'331'}}

    duplicate = Conversation()
    add_exchange(
        duplicate,
        'USER',
        '331',
        b'USER another\r\n',
        b'331 password\r\n',
    )
    berserker.analyze_cons(duplicate, trans_inc=0, type_inc=0)

    assert berserker.exe.saved_conversations == []
