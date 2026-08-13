import threading
import time
from types import SimpleNamespace

import voltron.fuzz as fuzz_module
from voltron.analyzer.analyzer import Analyzer
from voltron.analyzer.analyzer import analyzer
from voltron.configs import configs
from voltron.fuzz import Fuzzer


def _status_fields(path):
    return {
        key.strip(): value.strip()
        for line in path.read_text(encoding='utf-8').splitlines()
        if ':' in line
        for key, value in [line.split(':', 1)]
    }


def test_status_snapshot_is_atomic_and_serializes_concurrent_writers(
    tmp_path,
    monkeypatch,
):
    metric = Analyzer()
    now = time.time()
    metric.start_time = now - 2
    metric.target_name = 'demo'
    metric.pro_name = 'demo-protocol'
    metric.run_status = 'running'
    metric.active_phase = 'model_learning'
    metric.stage = 'model learning'
    metric.phase_metrics = {
        'model_learning': {'start_time': now - 1},
    }
    monkeypatch.setattr(configs, 'results_path', tmp_path, raising=False)

    assert metric.write_status_snapshot('startup') is True
    workers = [
        threading.Thread(
            target=metric.write_status_snapshot,
            args=('heartbeat',),
        )
        for _ in range(6)
    ]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join()

    status_file = tmp_path / 'diagnostics' / 'status' / 'fuzzer_status'
    fields = _status_fields(status_file)
    assert fields['run_status'] == 'running'
    assert fields['active_phase'] == 'model_learning'
    assert fields['stage'] == 'model learning'
    assert fields['status_sequence'] == '7'
    assert float(fields['phase_elapsed_seconds']) >= 0
    assert not list(
        (tmp_path / 'diagnostics' / 'status').glob('.fuzzer_status.*.tmp')
    )


def test_status_heartbeat_refreshes_then_stops(monkeypatch):
    fuzzer = Fuzzer.__new__(Fuzzer)
    fuzzer.mode = 'fuzz'
    fuzzer.stop_event = threading.Event()
    snapshots = []
    snapshot_lock = threading.Lock()

    def write_snapshot(reason):
        with snapshot_lock:
            snapshots.append(reason)
        return True

    fuzzer._write_status_snapshot = write_snapshot
    monkeypatch.setattr(
        configs,
        'status_snapshot_interval_s',
        0.01,
        raising=False,
    )

    fuzzer._start_status_heartbeat()
    deadline = time.monotonic() + 1
    while time.monotonic() < deadline:
        with snapshot_lock:
            if len(snapshots) >= 2:
                break
        time.sleep(0.005)
    fuzzer._stop_status_heartbeat()
    with snapshot_lock:
        count_after_stop = len(snapshots)
    time.sleep(0.03)

    with snapshot_lock:
        assert snapshots
        assert all(reason == 'heartbeat' for reason in snapshots)
        assert len(snapshots) == count_after_stop
    assert fuzzer._status_heartbeat_thread is None


def test_replay_mode_does_not_start_status_heartbeat(monkeypatch):
    fuzzer = Fuzzer.__new__(Fuzzer)
    fuzzer.mode = 'replay'
    fuzzer.stop_event = threading.Event()
    calls = []
    fuzzer._write_status_snapshot = lambda reason: calls.append(reason)
    monkeypatch.setattr(
        configs,
        'status_snapshot_interval_s',
        0.01,
        raising=False,
    )

    fuzzer._start_status_heartbeat()
    time.sleep(0.03)

    assert calls == []
    assert not hasattr(fuzzer, '_status_heartbeat_thread')


def test_runtime_config_reads_status_snapshot_interval(tmp_path, monkeypatch):
    runtime_config = {
        'demo': {
            'protocol': 'demo-protocol',
            'host': '127.0.0.1',
            'port': 1,
            'rfc_name': [],
            'trans_layer': 'tcp',
            'server': 'parent',
        },
        'llm_doc': {
            'base_url': 'http://doc.example',
            'api_key': 'doc-key',
            'model': 'doc-model',
            'async_sem': 1,
        },
        'llm_fuzz': {
            'base_url': 'http://fuzz.example',
            'api_key': 'fuzz-key',
            'model': 'fuzz-model',
            'async_sem': 1,
        },
        'llm_compliance': {
            'base_url': 'http://compliance.example',
            'api_key': 'compliance-key',
            'model': 'compliance-model',
            'async_sem': 1,
        },
        'status_reporting': {'interval_seconds': 0.125},
    }
    fuzzer = Fuzzer.__new__(Fuzzer)
    fuzzer.target_name = 'demo'
    fuzzer.output = 'out'
    fuzzer.mode = 'fuzz'
    fuzzer.spec_knowledge = True
    fuzzer.state_learning = True
    fuzzer.guided_scheduling = True
    fuzzer.compliance_analysis = False
    fuzzer.observer_enabled = True
    monkeypatch.setattr(configs, 'base_path', tmp_path, raising=False)
    monkeypatch.setattr(
        fuzz_module,
        'load_runtime_config',
        lambda _config_dir: runtime_config,
    )

    fuzzer.load_configs()

    assert configs.status_snapshot_interval_s == 0.125
    assert configs.partial_guidance_enabled is True
    assert configs.reuse_imported_partial_guidance is True


def test_fuzz_writes_startup_and_final_status_snapshots(tmp_path, monkeypatch):
    fuzzer = Fuzzer.__new__(Fuzzer)
    fuzzer.target_name = 'demo'
    fuzzer.mode = 'fuzz'
    fuzzer.stop_event = threading.Event()
    fuzzer._cleanup_lock = threading.RLock()
    fuzzer._cleanup_done = False
    fuzzer._previous_sigint_handler = None
    fuzzer._signal_handler_installed = False
    fuzzer._worker_threads = []
    fuzzer.mapper = SimpleNamespace(close=lambda: None)
    fuzzer.exe = SimpleNamespace(run_controller=None)
    fuzzer.state_fuzz = lambda stop_event: stop_event.set()
    fuzzer._install_signal_handlers = lambda: None
    fuzzer._restore_signal_handlers = lambda: None
    fuzzer._terminate_active_sut = lambda *_args, **_kwargs: None
    monkeypatch.setattr(fuzz_module, 'ui_loop', lambda _event: None)
    monkeypatch.setattr(configs, 'results_path', tmp_path, raising=False)
    monkeypatch.setattr(
        configs,
        'status_snapshot_interval_s',
        0,
        raising=False,
    )
    analyzer.reset_phase_metrics()
    analyzer.sut_proc = None
    analyzer.target_name = 'demo'
    analyzer.pro_name = 'demo-protocol'
    analyzer.stop_reason = None

    assert fuzzer.fuzz('state', 1) == 2

    fields = _status_fields(
        tmp_path / 'diagnostics' / 'status' / 'fuzzer_status'
    )
    assert fields['run_status'] == 'incomplete'
    assert fields['snapshot_reason'] == 'collect_results'
    assert int(fields['status_sequence']) >= 2
