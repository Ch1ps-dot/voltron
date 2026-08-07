import threading

from voltron.configs import configs
from voltron.learner.mlstar import ObTable


def test_empty_membership_query_is_retried_before_learning_fails(monkeypatch):
    responses = iter([[], [], ['PONG']])
    table = ObTable.__new__(ObTable)
    table.stop_event = threading.Event()
    table.mq = type('MQ', (), {'query': lambda _self, _word: next(responses)})()

    monkeypatch.setattr(
        configs,
        'model_learning_empty_response_retries',
        3,
        raising=False,
    )

    assert table._query_with_empty_retry(('PING',)) == ['PONG']
    assert not table.stop_event.is_set()
