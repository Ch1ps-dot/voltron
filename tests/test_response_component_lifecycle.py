import queue
import threading
import json
from types import SimpleNamespace

from voltron.configs import configs
from voltron.executor.executor import (
    CheckerEvaluation,
    Executor,
    ObservationResult,
)
from voltron.synthesizer.synthesizer import AsyncProducer
from voltron.synthesizer.checker import Checker
from voltron.synthesizer.observer import ResponseObserver


def make_producer() -> AsyncProducer:
    producer = AsyncProducer.__new__(AsyncProducer)
    producer.rfcp = SimpleNamespace(
        res_type_rules={
            "types": [
                {"type_name": "200"},
                {"type_name": "404"},
                {"type_name": "481"},
            ]
        }
    )
    producer.checkers = {}
    producer.observers = {}
    producer._response_component_lock = threading.RLock()
    producer._response_component_pending = set()
    producer._response_component_failures = set()
    producer._response_component_queue = queue.Queue()
    producer._response_component_worker = None
    producer._primary_response_field_name = lambda: "Status-Code"
    producer._response_component_ir_sha256 = lambda response_type: (
        f"ir:{response_type}"
    )
    return producer


def test_lazy_initial_components_are_generic_plus_explicit_prewarm():
    producer = make_producer()
    old_lazy = configs.response_component_lazy_generation
    old_prewarm = configs.response_component_prewarm_types
    try:
        configs.response_component_lazy_generation = True
        configs.response_component_prewarm_types = ["404", "UNKNOWN", "404"]

        assert producer._initial_response_component_types() == [
            "__all__",
            "404",
        ]
    finally:
        configs.response_component_lazy_generation = old_lazy
        configs.response_component_prewarm_types = old_prewarm


def test_component_candidates_use_exact_family_then_generic():
    producer = make_producer()

    assert producer.response_component_candidates("SIP/2.0 404 Not Found") == [
        "SIP/2.0 404 Not Found",
        "4xx",
        "__all__",
    ]
    assert producer.response_component_candidates("PUBACK_SUCCESS") == [
        "PUBACK_SUCCESS",
        "__all__",
    ]


def test_stale_cached_component_is_regenerated_instead_of_counted_present():
    producer = make_producer()
    producer._primary_response_field_name = lambda: "Status-Code"
    producer._response_component_ir_sha256 = lambda _response_type: "new-ir"
    producer.checkers["__all__"] = [
        Checker("__all__", "init", "id0", "", state_field="Old-Field")
    ]
    producer.observers["__all__"] = [
        ResponseObserver("__all__", "id0", "", state_field="Old-Field")
    ]

    assert producer._missing_checker_types(["__all__"]) == ["__all__"]
    assert producer._missing_observer_types(["__all__"]) == ["__all__"]
    assert "__all__" not in producer.checkers
    assert "__all__" not in producer.observers


def test_on_demand_generation_is_deduplicated_and_nonblocking():
    producer = make_producer()
    calls = []

    def checker_gen(response_types):
        calls.append(("checker", tuple(response_types)))
        for response_type in response_types:
            producer.checkers[response_type] = [SimpleNamespace(
                state_field="Status-Code",
                contract_version=producer.RESPONSE_COMPONENT_CONTRACT_VERSION,
                ir_sha256=f"ir:{response_type}",
            )]

    def observer_gen(response_types):
        calls.append(("observer", tuple(response_types)))
        for response_type in response_types:
            producer.observers[response_type] = [SimpleNamespace(
                state_field="Status-Code",
                contract_version=producer.RESPONSE_COMPONENT_CONTRACT_VERSION,
                ir_sha256=f"ir:{response_type}",
            )]

    producer.checker_gen = checker_gen
    producer.observer_gen = observer_gen
    old_spec = configs.spec_knowledge
    old_lazy = configs.response_component_lazy_generation
    try:
        configs.spec_knowledge = True
        configs.response_component_lazy_generation = True
        producer.request_response_components("404")
        producer.request_response_components("404")
        assert producer.wait_for_response_components(timeout=2)
    finally:
        configs.spec_knowledge = old_spec
        configs.response_component_lazy_generation = old_lazy

    assert producer.checkers.keys() == {"404", "4xx"}
    assert producer.observers.keys() == {"404", "4xx"}
    assert calls.count(("checker", ("404",))) == 1
    assert calls.count(("observer", ("404",))) == 1
    assert calls.count(("checker", ("4xx",))) == 1
    assert calls.count(("observer", ("4xx",))) == 1


def test_on_demand_generation_skips_observers_when_disabled():
    producer = make_producer()
    calls = []

    def checker_gen(response_types):
        calls.append(("checker", tuple(response_types)))
        for response_type in response_types:
            producer.checkers[response_type] = [SimpleNamespace(
                state_field="Status-Code",
                contract_version=producer.RESPONSE_COMPONENT_CONTRACT_VERSION,
                ir_sha256=f"ir:{response_type}",
            )]

    producer.checker_gen = checker_gen
    producer.observer_gen = lambda _response_types: calls.append(("observer",))
    old_spec = configs.spec_knowledge
    old_lazy = configs.response_component_lazy_generation
    old_enabled = configs.observer_enabled
    try:
        configs.spec_knowledge = True
        configs.response_component_lazy_generation = True
        configs.observer_enabled = False
        producer.request_response_components("404")
        assert producer.wait_for_response_components(timeout=2)
    finally:
        configs.spec_knowledge = old_spec
        configs.response_component_lazy_generation = old_lazy
        configs.observer_enabled = old_enabled

    assert calls == [("checker", ("404",)), ("checker", ("4xx",))]
    assert producer.observers == {}


def make_executor() -> Executor:
    executor = Executor.__new__(Executor)
    executor.mapper = SimpleNamespace(producer=None)
    executor.checker_funcs = {}
    executor.observer_funcs = {}
    executor.observer_sources = {}
    return executor


def test_checker_result_distinguishes_exact_uncertain_and_unchecked():
    executor = make_executor()
    executor.checker_funcs = {
        "200": lambda response: True,
        "4xx": lambda response: True,
        "__all__": lambda response: False,
    }

    exact = executor.evaluate_response("200", b"response")
    family = executor.evaluate_response("404", b"response")
    generic_rejection = executor.evaluate_response("777", b"response")
    executor.checker_funcs = {}
    unchecked = executor.evaluate_response("200", b"response")

    assert (exact.status, exact.scope) == ("compliant", "exact")
    assert (family.status, family.scope) == ("uncertain", "family")
    assert generic_rejection.status == "non_compliant"
    assert unchecked.status == "unchecked"
    assert executor.check_response("200", b"response") is True


def test_observer_reports_both_fingerprints_and_provisional_scope():
    executor = make_executor()
    executor.observer_funcs = {"4xx": lambda response: "a" * 64}

    family = executor.observe_response_result("404", b"dynamic response")
    executor.observer_funcs["404"] = lambda response: "b" * 64
    exact = executor.observe_response_result("404", b"dynamic response")

    assert family.semantic_fingerprint == "a" * 64
    assert family.raw_fingerprint != family.semantic_fingerprint
    assert family.scope == "family"
    assert family.provisional is True
    assert exact.scope == "exact"
    assert exact.provisional is False


def test_component_usage_summary_keeps_four_state_and_provisional_counts(
    tmp_path,
    monkeypatch,
):
    executor = make_executor()
    monkeypatch.setattr(configs, "results_path", tmp_path, raising=False)
    executor._record_response_component_usage(
        "INVITE",
        "404",
        CheckerEvaluation("unchecked", "none", None, "missing"),
        ObservationResult(
            "a" * 64,
            "b" * 64,
            "generic",
            "__all__",
            True,
        ),
    )

    summary = json.loads(
        (tmp_path / "response_component_summary.json").read_text(
            encoding="utf-8"
        )
    )
    assert summary["observed_response_types"] == ["404"]
    assert summary["checker_status"] == {"unchecked": 1}
    assert summary["observer_provisional_count"] == 1
    assert len((
        tmp_path / "response_component_usage.jsonl"
    ).read_text(encoding="utf-8").splitlines()) == 1
