import json
from http.client import HTTPConnection
from pathlib import Path
import threading

from voltron.web.app import (
    create_server,
    parse_key_value_status,
    read_csv,
    summarize_states,
    target_catalog,
)


def _write_config(root: Path) -> None:
    config = root / 'config'
    config.mkdir()
    (config / 'configs.yaml').write_text(
        """
demo:
  protocol: ftp
  host: 127.0.0.1
  port: 2121
  trans_layer: tcp
  rfc_name: [rfc959]
executor:
  setup_timeout_seconds: 1
""",
        encoding='utf-8',
    )


def test_status_and_csv_adapters_coerce_numbers(tmp_path):
    status = tmp_path / 'fuzzer_status'
    status.write_text(
        'run_status       : running\nexec_path_num    : 42\nrate: 2.5\n',
        encoding='utf-8',
    )
    metrics = tmp_path / 'metrics.csv'
    metrics.write_text('phase,duration_s\nfuzzing,1.25\n', encoding='utf-8')

    assert parse_key_value_status(status) == {
        'run_status': 'running',
        'exec_path_num': 42,
        'rate': 2.5,
    }
    assert read_csv(metrics) == [{'phase': 'fuzzing', 'duration_s': 1.25}]


def test_target_catalog_excludes_global_config(tmp_path):
    _write_config(tmp_path)

    assert target_catalog(tmp_path) == [{
        'name': 'demo',
        'protocol': 'ftp',
        'host': '127.0.0.1',
        'port': 2121,
        'transport': 'TCP',
        'deployment': 'local',
        'rfc_count': 1,
    }]


def test_state_summary_reads_snapshot_counts():
    summary = summarize_states([
        {'data_type': 'nodes', 'data': '1', 'elapsed_seconds': '2.5'},
        {'data_type': 'edges', 'data': '0', 'elapsed_seconds': '2.5'},
        {'data_type': 'nodes', 'data': '2', 'elapsed_seconds': '4.0'},
        {'data_type': 'edges', 'data': '1', 'elapsed_seconds': '4.0'},
    ])

    assert summary['nodes'] == 2
    assert summary['edges'] == 1
    assert summary['discoveries'][-1] == {
        'time': 4.0, 'nodes': 2, 'edges': 1,
    }


def test_http_server_serves_dashboard_and_target_api(tmp_path):
    _write_config(tmp_path)
    server = create_server('127.0.0.1', 0, tmp_path)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    connection = HTTPConnection('127.0.0.1', server.server_port, timeout=2)
    try:
        connection.request('GET', '/')
        response = connection.getresponse()
        page = response.read().decode('utf-8')
        connection.request('GET', '/api/targets')
        response = connection.getresponse()
        payload = json.loads(response.read())
    finally:
        connection.close()
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)

    assert '<title>Voltron · Fuzz Operations</title>' in page
    assert payload['targets'][0]['name'] == 'demo'
