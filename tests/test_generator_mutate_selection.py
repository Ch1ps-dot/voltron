from voltron.configs import configs
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
