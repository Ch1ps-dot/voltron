import json
from pathlib import Path

from voltron.configs import configs
from voltron.executor.conversation import Conversation
from voltron.executor.executor import Executor
from voltron.learner.equ_oracle import EquOracle
from voltron.learner.mem_oracle import MembershipOracle
from voltron.scheduler.seed_retention import SeedRetentionPolicy
from voltron.analyzer.analyzer import analyzer


def make_conversation(request: bytes = b'PING\r\n') -> Conversation:
    conversation = Conversation()
    conversation.add_state('PING', 'PONG')
    conversation.add_data(request, b'PONG\r\n')
    return conversation


def make_response_sequence(response_types: list[str]) -> Conversation:
    conversation = Conversation()
    for index, response_type in enumerate(response_types):
        conversation.add_state('PING', response_type)
        conversation.add_data(
            f'PING {index}\r\n'.encode(),
            f'{response_type}\r\n'.encode(),
        )
    return conversation


def test_longer_response_sequence_is_seed_novelty():
    assert SeedRetentionPolicy.is_interesting(
        transition_increment=0,
        response_type_increment=0,
        sequence_length_increment=4,
        unique_response_increment=3,
        request_response_increment=0,
    )
    assert not SeedRetentionPolicy.is_interesting(
        transition_increment=0,
        response_type_increment=0,
        sequence_length_increment=0,
        unique_response_increment=3,
        request_response_increment=0,
    )


def test_only_transition_or_response_type_is_seed_novelty():
    assert SeedRetentionPolicy.is_interesting(1, 0, 0, 0, 0)
    assert SeedRetentionPolicy.is_interesting(0, 1, 0, 0, 0)
    assert not SeedRetentionPolicy.is_interesting(0, 0, 0, 0, 1)


def test_more_distinct_response_transitions_is_seed_novelty():
    assert SeedRetentionPolicy.is_interesting(
        transition_increment=0,
        response_type_increment=0,
        sequence_length_increment=0,
        unique_response_increment=0,
        request_response_increment=0,
        unique_transition_increment=2,
    )


def test_observe_tracks_record_response_transition_variety():
    retention = SeedRetentionPolicy()

    baseline = make_response_sequence(['A', 'A', 'A', 'A'])
    assert retention.observe(baseline, 0, 0).interesting

    richer_same_length = make_response_sequence(['B', 'C', 'D', 'E'])
    novelty = retention.observe(richer_same_length, 0, 0)

    assert novelty.interesting
    assert retention.max_sequence_length == 4
    assert retention.max_unique_transition_count == 3


def test_model_learning_retains_only_interesting_conversations_as_seeds(monkeypatch):
    conversation = make_conversation()
    response_type_count = [0]
    monkeypatch.setattr(analyzer, 'res_types_num', lambda: response_type_count[0])

    class Mapper:
        def select_generators(self, *_args, **_kwargs):
            return [('PING', b'PING\r\n')]

        request_types = {'PING'}

    class ExecutorStub:
        def __init__(self):
            self.saved = []
            self.discovered_response_type = False

        def interact(self, _messages):
            if not self.discovered_response_type:
                response_type_count[0] += 1
                self.discovered_response_type = True
            return True, conversation

        def save_cons(self, saved_conversation, **_kwargs):
            self.saved.append(saved_conversation)
            return True

    executor = ExecutorStub()
    oracle = MembershipOracle(Mapper(), executor)

    assert oracle.query(('PING',)) == ['PONG']
    assert executor.saved == [conversation]
    assert oracle.query(('PING',)) == ['PONG']
    assert executor.saved == [conversation]


def test_equivalence_queries_also_retain_valid_model_learning_seeds(monkeypatch):
    conversation = make_conversation()
    response_type_count = [0]
    monkeypatch.setattr(analyzer, 'res_types_num', lambda: response_type_count[0])

    class Mapper:
        def select_generators(self, _word):
            return [('PING', b'PING\r\n')]

    class ExecutorStub:
        def __init__(self):
            self.saved = []

        def interact(self, _messages):
            response_type_count[0] += 1
            return True, conversation

        def save_cons(self, saved_conversation, **_kwargs):
            self.saved.append(saved_conversation)
            return True

    executor = ExecutorStub()
    oracle = EquOracle(Mapper(), executor)

    assert oracle.query(['PING']) == [(b'PING\r\n', b'PONG\r\n')]
    assert executor.saved == [conversation]


def test_membership_and_equivalence_share_model_learning_novelty_state(monkeypatch):
    conversation = make_conversation()
    response_type_count = [0]
    monkeypatch.setattr(analyzer, 'res_types_num', lambda: response_type_count[0])

    class Mapper:
        request_types = {'PING'}

        def select_generators(self, *_args, **_kwargs):
            return [('PING', b'PING\r\n')]

    class ExecutorStub:
        def __init__(self):
            self.saved = []
            self.discovered_response_type = False

        def interact(self, _messages):
            if not self.discovered_response_type:
                response_type_count[0] += 1
                self.discovered_response_type = True
            return True, conversation

        def save_cons(self, saved_conversation, **_kwargs):
            self.saved.append(saved_conversation)
            return True

    executor = ExecutorStub()
    retention = SeedRetentionPolicy()
    membership = MembershipOracle(Mapper(), executor, retention)
    equivalence = EquOracle(Mapper(), executor, retention)

    assert membership.query(('PING',)) == ['PONG']
    assert equivalence.query(['PING']) == [(b'PING\r\n', b'PONG\r\n')]
    assert executor.saved == [conversation]


def test_replayable_seed_deduplication_spans_model_learning_and_fuzzing(
    tmp_path: Path,
    monkeypatch,
):
    monkeypatch.setattr(configs, 'results_path', tmp_path, raising=False)
    monkeypatch.setattr(analyzer, 'active_phase', 'model_learning', raising=False)
    monkeypatch.setattr(
        analyzer, '_state_snapshot_phase', 'model_learning', raising=False,
    )
    monkeypatch.setattr(
        analyzer, '_state_snapshot_phase_iteration', 7, raising=False,
    )
    monkeypatch.setattr(
        analyzer, '_state_snapshot_components', (), raising=False,
    )
    executor = Executor.__new__(Executor)
    learning_seed = make_conversation()
    duplicate_fuzzing_seed = make_conversation()
    distinct_fuzzing_seed = make_conversation(b'PING second\r\n')

    assert executor.save_cons(
        learning_seed,
        source='membership_oracle',
        retention_reasons=('new_response_type',),
    ) is True
    assert executor.save_cons(duplicate_fuzzing_seed) is False
    assert executor.save_cons(distinct_fuzzing_seed) is True

    replayable = sorted((tmp_path / 'replayable_testcases').glob('cons_*.pkl'))
    assert len(replayable) == 2
    manifest = (
        tmp_path / 'diagnostics' / 'events' / 'replayable_seed_manifest.jsonl'
    )
    records = [json.loads(line) for line in manifest.read_text().splitlines()]
    assert [record['sequence_file'] for record in records] == [
        'replayable_testcases/cons_000000.pkl',
        'replayable_testcases/cons_000001.pkl',
    ]
    assert all(record['phase'] == 'model_learning' for record in records)
    assert all(record['phase_iteration'] == 7 for record in records)
    assert all(record['seed_sha256'] for record in records)
    assert all('request_types' in record for record in records)
    assert records[0]['source'] == 'membership_oracle'
    assert records[0]['retention_reasons'] == ['new_response_type']
