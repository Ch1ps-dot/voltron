from voltron.configs import configs
from voltron.analyzer.analyzer import analyzer
from voltron.synthesizer.synthesizer import AsyncProducer


def make_producer(req_types: set[str]) -> AsyncProducer:
    producer = AsyncProducer.__new__(AsyncProducer)
    producer.req_types = req_types
    return producer


def test_generator_mutate_selects_one_quarter_of_types_round_robin():
    original_async_sem = getattr(configs, 'async_sem_fuzz', None)
    original_ratio = getattr(configs, 'mutator_round_ratio', None)
    try:
        configs.async_sem_fuzz = 8
        configs.mutator_round_ratio = 0.25
        producer = make_producer({'A', 'B', 'C', 'D'})

        assert producer._select_generator_mutate_types() == ['A']
        assert producer._select_generator_mutate_types() == ['B']
        assert producer._select_generator_mutate_types() == ['C']
        assert producer._select_generator_mutate_types() == ['D']
        assert producer._select_generator_mutate_types() == ['A']
    finally:
        if original_async_sem is None:
            delattr(configs, 'async_sem_fuzz')
        else:
            configs.async_sem_fuzz = original_async_sem
        if original_ratio is None:
            delattr(configs, 'mutator_round_ratio')
        else:
            configs.mutator_round_ratio = original_ratio


def test_generator_mutate_selection_caps_at_request_type_count():
    original_async_sem = getattr(configs, 'async_sem_fuzz', None)
    original_ratio = getattr(configs, 'mutator_round_ratio', None)
    try:
        configs.async_sem_fuzz = 8
        configs.mutator_round_ratio = 1.0
        producer = make_producer({'A', 'B', 'C'})

        assert producer._select_generator_mutate_types() == ['A', 'B', 'C']
    finally:
        if original_async_sem is None:
            delattr(configs, 'async_sem_fuzz')
        else:
            configs.async_sem_fuzz = original_async_sem
        if original_ratio is None:
            delattr(configs, 'mutator_round_ratio')
        else:
            configs.mutator_round_ratio = original_ratio


def test_generator_mutate_ratio_is_capped_by_llm_concurrency():
    original_async_sem = getattr(configs, 'async_sem_fuzz', None)
    original_ratio = getattr(configs, 'mutator_round_ratio', None)
    try:
        configs.async_sem_fuzz = 2
        configs.mutator_round_ratio = 0.25
        producer = make_producer({str(index) for index in range(12)})

        assert producer._select_generator_mutate_types() == ['0', '1']
        assert producer._select_generator_mutate_types() == ['10', '11']
    finally:
        if original_async_sem is None:
            delattr(configs, 'async_sem_fuzz')
        else:
            configs.async_sem_fuzz = original_async_sem
        if original_ratio is None:
            delattr(configs, 'mutator_round_ratio')
        else:
            configs.mutator_round_ratio = original_ratio


def test_generator_mutate_records_selected_types_before_mutation(
    tmp_path,
    monkeypatch,
):
    producer = make_producer({'A', 'B', 'C'})
    producer.info_path = tmp_path / "info.md"
    producer.info_path.write_text("protocol info", encoding="utf-8")
    producer.mutator_path = tmp_path / "mutators"
    producer.mutator_path.mkdir()
    producer.mutator_info_path = tmp_path / "mutator_info.json"
    producer.mutators = {}
    producer.generators = {}
    producer.mutator_info = lambda: {}

    async def no_mutations(*_args, **_kwargs):
        return []

    producer._generator_mutate_async = no_mutations
    monkeypatch.setattr(configs, "async_sem_fuzz", 2, raising=False)
    checkpoints = []
    monkeypatch.setattr(
        analyzer,
        "record_generator_checkpoint",
        lambda **kwargs: checkpoints.append(kwargs),
    )

    assert producer.generator_mutate({}, iteration=4) == []

    assert checkpoints == [{
        "phase": "fuzzing",
        "checkpoint_type": "before_generator_mutate",
        "phase_iteration": 4,
        "operation_id": "mutate-4",
        "mutated_types": ["A"],
    }]
