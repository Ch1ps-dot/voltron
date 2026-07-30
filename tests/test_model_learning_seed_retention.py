from pathlib import Path

from voltron.configs import configs
from voltron.executor.conversation import Conversation
from voltron.executor.executor import Executor
from voltron.learner.equ_oracle import EquOracle
from voltron.learner.mem_oracle import MembershipOracle


def make_conversation(request: bytes = b'PING\r\n') -> Conversation:
    conversation = Conversation()
    conversation.add_state('PING', 'PONG')
    conversation.add_data(request, b'PONG\r\n')
    return conversation


def test_model_learning_retains_each_valid_conversation_as_a_seed():
    conversation = make_conversation()

    class Mapper:
        def select_generators(self, *_args, **_kwargs):
            return [('PING', b'PING\r\n')]

        request_types = {'PING'}

    class ExecutorStub:
        def __init__(self):
            self.saved = []

        def interact(self, _messages):
            return True, conversation

        def save_cons(self, saved_conversation):
            self.saved.append(saved_conversation)
            return True

    executor = ExecutorStub()
    oracle = MembershipOracle(Mapper(), executor)

    assert oracle.query(('PING',)) == ['PONG']
    assert executor.saved == [conversation]


def test_equivalence_queries_also_retain_valid_model_learning_seeds():
    conversation = make_conversation()

    class Mapper:
        def select_generators(self, _word):
            return [('PING', b'PING\r\n')]

    class ExecutorStub:
        def __init__(self):
            self.saved = []

        def interact(self, _messages):
            return True, conversation

        def save_cons(self, saved_conversation):
            self.saved.append(saved_conversation)
            return True

    executor = ExecutorStub()
    oracle = EquOracle(Mapper(), executor)

    assert oracle.query(['PING']) == [(b'PING\r\n', b'PONG\r\n')]
    assert executor.saved == [conversation]


def test_replayable_seed_deduplication_spans_model_learning_and_fuzzing(
    tmp_path: Path,
    monkeypatch,
):
    monkeypatch.setattr(configs, 'results_path', tmp_path, raising=False)
    executor = Executor.__new__(Executor)
    learning_seed = make_conversation()
    duplicate_fuzzing_seed = make_conversation()
    distinct_fuzzing_seed = make_conversation(b'PING second\r\n')

    assert executor.save_cons(learning_seed) is True
    assert executor.save_cons(duplicate_fuzzing_seed) is False
    assert executor.save_cons(distinct_fuzzing_seed) is True

    replayable = sorted((tmp_path / 'replayable_testcases').glob('cons_*.pkl'))
    assert len(replayable) == 2
