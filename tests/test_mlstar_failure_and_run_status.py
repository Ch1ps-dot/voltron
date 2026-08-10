import json
import threading
import time
from types import SimpleNamespace

import pytest

from voltron.analyzer.analyzer import Analyzer, analyzer
from voltron.configs import configs
from voltron.fuzz import Fuzzer
from voltron.learner.mlstar import MealyLstar


def test_mlstar_run_propagates_original_learning_exception():
    learner = MealyLstar.__new__(MealyLstar)

    def fail_close():
        raise ValueError('table construction failed')

    learner.table = SimpleNamespace(
        make_close=fail_close,
        make_consistent=lambda: None,
        build_hypothesis=lambda _id: pytest.fail('must not build'),
    )

    with pytest.raises(ValueError, match='table construction failed'):
        learner.run('iteration-1')


def test_mlstar_berserker_run_propagates_original_learning_exception():
    learner = MealyLstar.__new__(MealyLstar)
    learner.table = SimpleNamespace(
        alphabet=['PING'],
        E=set(),
        table_init=lambda: (_ for _ in ()).throw(
            RuntimeError('mutated table failed')
        ),
    )

    with pytest.raises(RuntimeError, match='mutated table failed'):
        learner.berserker_run('iteration-2')


def test_analyzer_stop_reason_is_first_writer_and_maps_phase_status():
    metric = Analyzer()
    event = threading.Event()
    metric.stop_event = event

    metric.request_stop('deadline', event)
    metric.request_stop('failure', event)

    assert event.is_set()
    assert metric.stop_reason == 'deadline'
    assert metric.phase_stop_status() == 'deadline_reached'

    metric.stop_reason = 'failure'
    assert metric.phase_stop_status() == 'failed'


def test_finalize_run_status_requires_fuzz_phase_for_deadline_completion(
    tmp_path,
    monkeypatch,
):
    fuzzer = Fuzzer.__new__(Fuzzer)
    fuzzer.target_name = 'proftpd'
    fuzzer.time_limit_s = 60
    monkeypatch.setattr(configs, 'results_path', tmp_path, raising=False)
    monkeypatch.setattr(analyzer, 'start_time', time.time() - 60, raising=False)
    monkeypatch.setattr(analyzer, 'strategy', 'state', raising=False)
    monkeypatch.setattr(analyzer, 'stop_reason', 'deadline', raising=False)
    monkeypatch.setattr(analyzer, 'phase_metrics', {}, raising=False)

    assert fuzzer._finalize_run_status() == 2
    status = json.loads(
        (tmp_path / 'diagnostics' / 'status' / 'run_status.json').read_text(
            encoding='utf-8'
        )
    )
    assert status['run_status'] == 'deadline_before_fuzzing'
    assert status['exit_code'] == 2


def test_finalize_run_status_accepts_deadline_after_fuzz_phase(
    tmp_path,
    monkeypatch,
):
    fuzzer = Fuzzer.__new__(Fuzzer)
    fuzzer.target_name = 'proftpd'
    fuzzer.time_limit_s = 60
    monkeypatch.setattr(configs, 'results_path', tmp_path, raising=False)
    monkeypatch.setattr(analyzer, 'start_time', time.time() - 60, raising=False)
    monkeypatch.setattr(analyzer, 'strategy', 'state', raising=False)
    monkeypatch.setattr(analyzer, 'stop_reason', 'deadline', raising=False)
    monkeypatch.setattr(
        analyzer,
        'phase_metrics',
        {'fuzzing': {'status': 'deadline_reached'}},
        raising=False,
    )

    assert fuzzer._finalize_run_status() == 0
    status = json.loads(
        (tmp_path / 'diagnostics' / 'status' / 'run_status.json').read_text(
            encoding='utf-8'
        )
    )
    assert status['run_status'] == 'completed'
    assert status['exit_code'] == 0
