from voltron.configs import configs
from voltron.analyzer.analyzer import analyzer
from voltron.synthesizer.synthesizer import AsyncProducer


def make_producer(req_types: set[str]) -> AsyncProducer:
    producer = AsyncProducer.__new__(AsyncProducer)
    producer.req_types = req_types
    return producer


def test_generator_mutate_selects_configured_concurrency_count():
    original_async_sem = getattr(configs, 'async_sem_fuzz', None)
    try:
        configs.async_sem_fuzz = 2
        producer = make_producer({'A', 'B', 'C', 'D'})

        assert producer._select_generator_mutate_types() == ['A', 'B']
        assert producer._select_generator_mutate_types() == ['C', 'D']
        assert producer._select_generator_mutate_types() == ['A', 'B']
    finally:
        if original_async_sem is None:
            delattr(configs, 'async_sem_fuzz')
        else:
            configs.async_sem_fuzz = original_async_sem


def test_generator_mutate_selection_caps_at_request_type_count():
    original_async_sem = getattr(configs, 'async_sem_fuzz', None)
    try:
        configs.async_sem_fuzz = 8
        producer = make_producer({'A', 'B', 'C'})

        assert producer._select_generator_mutate_types() == ['A', 'B', 'C']
    finally:
        if original_async_sem is None:
            delattr(configs, 'async_sem_fuzz')
        else:
            configs.async_sem_fuzz = original_async_sem


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

    producer.generator_mutate({}, iteration=4)

    assert checkpoints == [{
        "phase": "fuzzing",
        "checkpoint_type": "before_generator_mutate",
        "phase_iteration": 4,
        "operation_id": "mutate-4",
        "mutated_types": ["A", "B"],
    }]
