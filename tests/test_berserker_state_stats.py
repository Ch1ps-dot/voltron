import pytest

from voltron.learner.automata import MealyMachine
from voltron.executor.conversation import Conversation
from voltron.scheduler.berserker import Berserker


class DummyMapper:
    request_types = {'USER', 'PASS'}
    req_dep = {}
    mutators = {}

    def select_generators(self, request_types):
        return [(request_type, b'data') for request_type in request_types if request_type != '-']


class DummyExecutor:
    pass


class FirstChoiceRandom:
    def choice(self, values):
        return values[0]


def make_machine():
    states = {('-',), ('-', 'USER'), ('-', 'USER', 'PASS')}
    transitions = {
        ('-',): {('USER',): ('331',)},
        ('-', 'USER'): {('PASS',): ('230',)},
    }
    return MealyMachine(
        id='test',
        states={1, 2, 3},
        alphabet={'USER', 'PASS'},
        delta={
            (1, 'USER'): 2,
            (2, 'PASS'): 3,
        },
        output={
            (1, 'USER'): '331',
            (2, 'PASS'): '230',
        },
        start=1,
        table=(states, set(), transitions),
    )


def test_records_state_depth_and_selection_count_in_memory():
    berserker = Berserker(
        mapper=DummyMapper(),
        exe=DummyExecutor(),
        machine=make_machine(),
    )
    berserker.rand = FirstChoiceRandom()

    assert berserker.state_stats[('-',)]['depth'] == 0
    assert berserker.state_stats[('-', 'USER')]['depth'] == 1
    assert berserker.state_stats[('-', 'USER', 'PASS')]['depth'] == 2

    berserker.select_base_state()
    berserker.select_base_state()

    selected_state = berserker.states[0]
    assert berserker.state_stats[selected_state]['call_count'] == 2
    assert sum(
        stats['call_count'] for stats in berserker.state_stats.values()
    ) == 2


def test_updates_reward_and_coverage_for_selected_state():
    berserker = Berserker(
        mapper=DummyMapper(),
        exe=DummyExecutor(),
        machine=make_machine(),
    )
    state = ('-', 'USER')
    prefix = berserker._use_machine_state(state, 'priority')
    request_sequence = prefix + [('PASS', b'PASS secret\r\n')]
    conversation = Conversation()
    conversation.add_state('USER', '331')
    conversation.add_data(b'USER test\r\n', b'331 password\r\n')
    conversation.add_state('PASS', 'CRASH')
    conversation.add_data(b'PASS secret\r\n', b'')

    berserker.update_state_feedback(
        request_sequence=request_sequence,
        prefix_length=len(prefix),
        transition_increment=1,
        response_increment=1,
        conversation=conversation,
    )

    stats = berserker.state_stats[state]
    assert stats['covered_transitions'] == {'PASS'}
    assert stats['total_reward'] == 9.2


def test_does_not_attribute_feedback_when_prefix_was_not_generated():
    berserker = Berserker(
        mapper=DummyMapper(),
        exe=DummyExecutor(),
        machine=make_machine(),
    )
    state = ('-', 'USER')
    berserker._use_machine_state(state, 'priority')

    berserker.update_state_feedback(
        request_sequence=[('PASS', b'data')],
        prefix_length=0,
        transition_increment=1,
        response_increment=1,
        conversation=Conversation(),
    )

    assert berserker.state_stats[state]['total_reward'] == 0.0


def test_timeout_does_not_receive_crash_reward():
    berserker = Berserker(
        mapper=DummyMapper(),
        exe=DummyExecutor(),
        machine=make_machine(),
    )
    state = ('-', 'USER')
    prefix = berserker._use_machine_state(state, 'priority')
    conversation = Conversation()
    conversation.add_state('USER', '331')
    conversation.add_data(b'USER test\r\n', b'331 password\r\n')
    conversation.add_state('PASS', 'TIMEOUT')
    conversation.add_data(b'PASS secret\r\n', b'')

    berserker.update_state_feedback(
        request_sequence=prefix + [('PASS', b'PASS secret\r\n')],
        prefix_length=len(prefix),
        transition_increment=0,
        response_increment=0,
        conversation=conversation,
    )

    stats = berserker.state_stats[state]
    assert stats['total_reward'] == 1.0


def test_priority_score_averages_normalized_reward_ucb_and_structure():
    berserker = Berserker(
        mapper=DummyMapper(),
        exe=DummyExecutor(),
        machine=make_machine(),
    )
    state = ('-', 'USER')
    berserker.state_stats[('-',)]['call_count'] = 1
    berserker.state_stats[state].update({
        'call_count': 2,
        'total_reward': 4.0,
        'covered_transitions': {'PASS'},
    })
    berserker.state_stats[('-', 'USER', 'PASS')]['call_count'] = 1

    # Reward is the global maximum (1), UCB is normalized against states with
    # one selection, and structure only contributes normalized depth because
    # this state's sole outgoing transition is already covered.
    expected_score = (1.0 + (2 / 3) ** 0.5 + 0.25) / 3

    assert berserker.calculate_state_priority(state) == pytest.approx(
        expected_score
    )
    assert berserker.select_priority_state() == state


def test_structure_uses_global_max_out_degree_for_uncovered_transitions():
    berserker = Berserker(
        mapper=DummyMapper(),
        exe=DummyExecutor(),
        machine=make_machine(),
    )
    root = ('-',)
    deep = ('-', 'USER', 'PASS')
    berserker.state_stats[root]['out_degree'] = 2

    # With no calls, reward and exploration are zero. The deep terminal state
    # gets depth value 1/2, while the root gets uncovered value 1/2.
    assert berserker.calculate_state_priority(root) == pytest.approx(1 / 6)
    assert berserker.calculate_state_priority(deep) == pytest.approx(1 / 6)
