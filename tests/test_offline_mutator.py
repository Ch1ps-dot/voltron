from voltron.scheduler.offline_mutator import OfflineMutator


def test_offline_mutator_is_deterministic_and_preserves_prefix_and_type():
    kwargs = dict(enabled=True, probability=1,
                  max_mutated_packets_per_sequence=1, max_mutations_per_packet=1,
                  max_delta_bytes=4, seed=7)
    first, first_changes = OfflineMutator(**kwargs).mutate_sequence(
        [('AUTH', b'auth'), ('DATA', b'payload')], prefix_length=1
    )
    second, second_changes = OfflineMutator(**kwargs).mutate_sequence(
        [('AUTH', b'auth'), ('DATA', b'payload')], prefix_length=1
    )
    assert first == second
    assert first[0] == ('AUTH', b'auth')
    assert first[1][0] == 'DATA'
    assert first[1][1]


def test_offline_mutator_can_be_disabled_and_mutates_imported_seed():
    sequence = [('DATA', b'payload')]
    assert OfflineMutator(enabled=False).mutate_sequence(sequence) == (sequence, [])
    mutated, changes = OfflineMutator(
        enabled=True, probability=1, seed=1, mutate_imported_seeds=True
    ).mutate_sequence(sequence, imported=True)
    assert mutated[0][0] == 'DATA'
    assert changes


def test_offline_mutator_protected_type_and_delta_limits():
    mutator = OfflineMutator(enabled=True, probability=1, seed=3,
                             protected_types=['AUTH'], max_delta_bytes=0)
    sequence, changes = mutator.mutate_sequence(
        [('AUTH', b'a'), ('DATA', b'b')]
    )
    assert sequence[0] == ('AUTH', b'a')
    assert all(
        delta == 0 or operator == 'length_extreme'
        for _index, operator, delta in changes
    )


def test_offline_mutator_randomly_mutates_bounded_distinct_packets():
    mutator = OfflineMutator(
        enabled=True, probability=1, seed=11,
        max_mutated_packets_per_sequence=3, max_mutations_per_packet=4,
    )
    sequence, changes = mutator.mutate_sequence(
        [('A', b'one'), ('B', b'two'), ('C', b'three'), ('D', b'four')],
    )
    affected = {index for index, _operator, _delta in changes}
    assert 1 <= len(affected) <= 3
    assert all(len(message) > 0 for _kind, message in sequence)
    assert all(abs(len(sequence[index][1]) - len((b'one', b'two', b'three', b'four')[index])) <= 4 for index in affected)


def test_imported_seed_option_overrides_prefix_protection():
    sequence = [('AFLNET', b'payload')]
    mutator = OfflineMutator(
        enabled=True, probability=1, seed=5, mutate_imported_seeds=True,
    )
    mutated, changes = mutator.mutate_sequence(
        sequence, prefix_length=0, imported=True,
    )
    assert changes
    assert mutated[0][0] == 'AFLNET'


def test_length_extreme_reaches_small_or_configured_large_bound():
    mutator = OfflineMutator(
        enabled=True, probability=1, seed=13, max_message_length=32,
        extreme_message_length=24,
    )
    results = {len(mutator._apply('length_extreme', b'payload')) for _ in range(16)}
    assert results <= {1, 24}
    assert results
