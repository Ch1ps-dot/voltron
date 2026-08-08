from types import SimpleNamespace

from voltron.executor.executor import Executor
from voltron.executor.mapper import Mapper


def test_mapper_attributes_selected_generator_to_its_evolution_round(
    monkeypatch,
):
    mapper = Mapper.__new__(Mapper)
    mapper.generators = {
        "PING": [SimpleNamespace(msg_type="PING", name="id2")],
    }
    mapper.message_pool = {}
    mapper.exec_retry_limit = 1
    mapper._component_evolution_rounds = {}
    mapper._message_provenance = {}
    monkeypatch.setattr(mapper, "_component_quarantined", lambda *_args: False)
    monkeypatch.setattr(mapper, "exe_generator", lambda _generator: b"PING")

    mapper.record_component_evolution("generator", ["PING"], "evolve-4")
    messages = mapper.select_generators(["PING"])

    assert messages == [("PING", b"PING")]
    assert mapper.consume_message_provenance(messages) == [{
        "request_type": "PING",
        "kind": "generator",
        "version": "id2",
        "evolve_round": "evolve-4",
    }]
    assert mapper._message_provenance == {}


def test_executor_forwards_components_with_active_parser_version():
    calls = []

    class SnapshotAnalyzer:
        def set_state_snapshot_components(self, *args):
            calls.append(args)

    executor = Executor.__new__(Executor)
    executor.analyzer = SnapshotAnalyzer()
    executor._parser_version = "id7"
    components = [{
        "request_type": "PING",
        "kind": "generator",
        "version": "id2",
        "evolve_round": "evolve-4",
    }]

    executor._set_state_snapshot_components(components, "PING")

    assert calls == [(components, "PING", "id7")]
