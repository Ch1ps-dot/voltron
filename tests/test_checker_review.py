import json
import threading
from pathlib import Path
from types import SimpleNamespace

from lxml import etree

from voltron.configs import configs
from voltron.executor.conversation import Conversation
from voltron.executor.executor import Executor
from voltron.synthesizer.checker import Checker
from voltron.synthesizer.observer import ResponseObserver
from voltron.synthesizer.synthesizer import AsyncProducer


class FakeProducer:
    def __init__(self, verdict: str) -> None:
        self.verdict = verdict
        self.review_calls = 0
        self.evolve_calls = 0
        self.semantic_compare_calls = 0

    def review_nonconforming_response(self, **kwargs):
        self.review_calls += 1
        self.operation_during_review = None
        return {
            "verdict": self.verdict,
            "summary": "reviewed",
            "violations": [],
            "evidence": [],
        }

    def evolve_checker(self, **kwargs):
        self.evolve_calls += 1
        return object()

    def responses_semantically_equivalent(self, **kwargs):
        self.semantic_compare_calls += 1
        return True


def make_executor(verdict: str):
    producer = FakeProducer(verdict)
    mapper = SimpleNamespace(
        producer=producer,
        equip_checkers=lambda: {"200": object()},
    )
    executor = Executor.__new__(Executor)
    executor.mapper = mapper
    executor.analyzer = SimpleNamespace(
        lock=threading.Lock(),
        non_compliant_num=0,
        current_operation="",
    )
    executor.checked_request_response_pairs = set()
    executor.reviewed_invalid_responses = set()
    executor.checked_response_samples = {}
    executor.reviewed_response_samples = {}
    executor.observer_evolution_failures = set()
    executor.observer_semantic_reviews = {}
    executor._invalid_response_lock = threading.Lock()
    executor.observer_funcs = {}
    return executor, producer


def make_conversation(
    request_type: str = "PING",
    response_type: str = "200",
    response: bytes = b"200 OK\r\n",
) -> Conversation:
    cons = Conversation()
    cons.add_state(request_type, response_type)
    cons.add_data(b"PING\r\n", response)
    return cons


def test_confirmed_violation_is_saved_once():
    executor, producer = make_executor("non_compliant")
    saved = []
    operations = []
    original_review = producer.review_nonconforming_response

    def review_with_operation(**kwargs):
        operations.append(executor.analyzer.current_operation)
        return original_review(**kwargs)

    producer.review_nonconforming_response = review_with_operation
    executor.save_invalid_response = (
        lambda cons, response_type, analysis=None:
        saved.append((response_type, analysis)) or True
    )

    cons = make_conversation()
    executor.handle_nonconforming_response(cons, "200")
    executor.handle_nonconforming_response(cons, "200")

    assert producer.review_calls == 1
    assert len(saved) == 1
    assert saved[0][1]["verdict"] == "non_compliant"
    assert executor.analyzer.non_compliant_num == 1
    assert operations == ["Checking possible non-compliance with LLM"]
    assert executor.analyzer.current_operation == ""


def test_persisted_invalid_response_is_deduplicated_across_executors(tmp_path):
    configs.results_path = tmp_path
    first_executor, _ = make_executor("non_compliant")
    second_executor, _ = make_executor("non_compliant")
    cons = make_conversation(
        request_type="CONNECT",
        response_type="405",
        response=b"HTTP/1.1 405 Method Not Allowed\r\n",
    )

    assert first_executor.save_invalid_response(
        cons,
        "405",
        analysis={"verdict": "non_compliant"},
    ) is True
    assert second_executor.save_invalid_response(
        cons,
        "405",
        analysis={"verdict": "non_compliant"},
    ) is False

    target = tmp_path / "invalid_responses"
    assert len(list(target.glob("cons_*.analysis.json"))) == 1
    assert len(list(target.glob("cons_*.pkl"))) == 1


def test_persisted_semantic_hash_deduplicates_dynamic_fields(tmp_path):
    configs.results_path = tmp_path
    first_executor, _ = make_executor("non_compliant")
    second_executor, _ = make_executor("non_compliant")
    semantic_observer = lambda response: "c" * 64
    first_executor.observer_funcs = {"405": semantic_observer}
    second_executor.observer_funcs = {"405": semantic_observer}
    first = make_conversation(
        request_type="CONNECT",
        response_type="405",
        response=b"HTTP/1.1 405\r\nDate: first\r\n\r\n",
    )
    second = make_conversation(
        request_type="CONNECT",
        response_type="405",
        response=b"HTTP/1.1 405\r\nDate: second\r\n\r\n",
    )

    assert first_executor.save_invalid_response(
        first,
        "405",
        analysis={"verdict": "non_compliant"},
    ) is True
    assert second_executor.save_invalid_response(
        second,
        "405",
        analysis={"verdict": "non_compliant"},
    ) is False

    records = list(
        (tmp_path / "invalid_responses").glob("cons_*.analysis.json")
    )
    assert len(records) == 1
    record = json.loads(records[0].read_text(encoding="utf-8"))
    assert record["response_observation"] == "c" * 64
    assert record["response_sha256"] != record["response_observation"]


def test_persisted_dedup_supports_legacy_analysis_without_hash(tmp_path):
    configs.results_path = tmp_path
    executor, _ = make_executor("non_compliant")
    cons = make_conversation(
        request_type="CONNECT",
        response_type="405",
        response=b"HTTP/1.1 405 Method Not Allowed\r\n",
    )
    target = tmp_path / "invalid_responses"
    target.mkdir()
    legacy = {
        "request_type": "CONNECT",
        "response_type": "405",
        "request": {"encoding": "base64", "data": ""},
        "response": {
            "encoding": "base64",
            "data": (
                "SFRUUC8xLjEgNDA1IE1ldGhvZCBOb3QgQWxsb3dlZA0K"
            ),
        },
        "analysis": {"verdict": "non_compliant"},
    }
    (target / "cons_000000.analysis.json").write_text(
        json.dumps(legacy),
        encoding="utf-8",
    )

    assert executor.save_invalid_response(
        cons,
        "405",
        analysis={"verdict": "non_compliant"},
    ) is False
    assert len(list(target.glob("cons_*.analysis.json"))) == 1


def test_compliant_false_positive_evolves_and_hot_reloads_checker():
    executor, producer = make_executor("compliant")
    loaded = []
    executor.load_checkers = lambda checkers: loaded.append(checkers)
    executor.save_invalid_response = lambda *args, **kwargs: None

    executor.handle_nonconforming_response(make_conversation(), "200")

    assert producer.evolve_calls == 1
    assert len(loaded) == 1
    assert executor.analyzer.current_operation == ""


def test_same_response_for_different_request_types_is_reviewed_separately():
    executor, producer = make_executor("uncertain")

    executor.handle_nonconforming_response(
        make_conversation(request_type="PING"),
        "200",
    )
    executor.handle_nonconforming_response(
        make_conversation(request_type="STATUS"),
        "200",
    )

    assert producer.review_calls == 2


def test_checker_is_skipped_outside_fuzzing():
    executor = Executor.__new__(Executor)
    executor.checked_request_response_pairs = set()
    executor._invalid_response_lock = threading.Lock()
    executor.observer_funcs = {}
    calls = []
    executor.check_response = (
        lambda response_type, response:
        calls.append((response_type, response)) or False
    )

    assert executor.check_response_during_fuzzing(
        "PING",
        "200",
        b"200 OK\r\n",
        enabled=False,
    ) is True
    assert calls == []


def test_checker_runs_during_fuzzing():
    executor = Executor.__new__(Executor)
    executor.checked_request_response_pairs = set()
    executor._invalid_response_lock = threading.Lock()
    executor.observer_funcs = {}
    calls = []
    executor.check_response = (
        lambda response_type, response:
        calls.append((response_type, response)) or False
    )

    assert executor.check_response_during_fuzzing(
        "PING",
        "200",
        b"invalid",
        enabled=True,
    ) is False
    assert calls == [("200", b"invalid")]


def test_duplicate_request_response_pair_is_skipped_before_checker():
    executor = Executor.__new__(Executor)
    executor.checked_request_response_pairs = set()
    executor._invalid_response_lock = threading.Lock()
    executor.observer_funcs = {}
    calls = []
    executor.check_response = (
        lambda response_type, response:
        calls.append((response_type, response)) or False
    )

    first = executor.check_response_during_fuzzing(
        "PING",
        "200",
        b"invalid",
        enabled=True,
    )
    duplicate = executor.check_response_during_fuzzing(
        "PING",
        "200",
        b"invalid",
        enabled=True,
    )

    assert first is False
    assert duplicate is True
    assert calls == [("200", b"invalid")]


def test_different_request_bytes_with_same_types_and_response_are_deduplicated():
    executor = Executor.__new__(Executor)
    executor.checked_request_response_pairs = set()
    executor._invalid_response_lock = threading.Lock()
    executor.observer_funcs = {}
    calls = []
    executor.check_response = (
        lambda response_type, response:
        calls.append((response_type, response)) or True
    )

    executor.check_response_during_fuzzing(
        "USER",
        "331",
        b"331 password\r\n",
        enabled=True,
    )
    executor.check_response_during_fuzzing(
        "USER",
        "331",
        b"331 password\r\n",
        enabled=True,
    )

    assert len(calls) == 1


def test_semantic_observer_deduplicates_dynamic_response_fields():
    executor = Executor.__new__(Executor)
    executor.checked_request_response_pairs = set()
    executor._invalid_response_lock = threading.Lock()
    executor.checked_response_samples = {}
    executor.reviewed_response_samples = {}
    executor.observer_evolution_failures = set()
    executor.observer_funcs = {
        "405": lambda response: (
            "a" * 64
            if response.startswith(b"HTTP/1.1 405")
            else "b" * 64
        )
    }
    calls = []
    executor.check_response = (
        lambda response_type, response:
        calls.append((response_type, response)) or True
    )

    executor.check_response_during_fuzzing(
        "CONNECT",
        "405",
        b"HTTP/1.1 405\r\nDate: first\r\n\r\n",
        enabled=True,
    )
    executor.check_response_during_fuzzing(
        "CONNECT",
        "405",
        b"HTTP/1.1 405\r\nDate: second\r\n\r\n",
        enabled=True,
    )

    assert len(calls) == 1


def test_invalid_observer_output_falls_back_to_raw_sha256():
    executor = Executor.__new__(Executor)
    executor.observer_funcs = {"200": lambda response: "not-a-hash"}
    response = b"200 OK\r\n"

    assert executor.observe_response("200", response) == __import__(
        "hashlib"
    ).sha256(response).hexdigest()


def test_observer_evolution_reobservees_memory_and_persisted_results(
    tmp_path,
):
    configs.results_path = tmp_path
    executor, producer = make_executor("non_compliant")
    first = b"HTTP/1.1 405\r\nDate: first\r\n\r\n"
    second = b"HTTP/1.1 405\r\nDate: second\r\n\r\n"
    executor.observer_funcs = {
        "405": lambda response: __import__("hashlib").sha256(
            response
        ).hexdigest()
    }
    checker_calls = []
    executor.check_response = (
        lambda response_type, response:
        checker_calls.append(response) or True
    )
    producer.observers = {"405": [object()]}
    producer.evolve_calls = 0

    def evolve_observer(response_type, samples):
        producer.evolve_calls += 1
        executor.observer_funcs = {"405": lambda response: "d" * 64}
        return object()

    producer.evolve_observer = evolve_observer
    executor.mapper.observers = producer.observers
    executor.mapper.equip_observers = lambda: {"405": object()}
    executor.load_observers = lambda observers: None

    assert executor.check_response_during_fuzzing(
        "CONNECT",
        "405",
        first,
        enabled=True,
    ) is True

    target = tmp_path / "invalid_responses"
    target.mkdir()
    record_path = target / "cons_000000.analysis.json"
    record_path.write_text(json.dumps({
        "request_type": "CONNECT",
        "response_type": "405",
        "response_sha256": __import__("hashlib").sha256(first).hexdigest(),
        "response_observation": __import__("hashlib").sha256(first).hexdigest(),
        "response": {
            "encoding": "base64",
            "data": __import__("base64").b64encode(first).decode("ascii"),
        },
    }), encoding="utf-8")

    assert executor.check_response_during_fuzzing(
        "CONNECT",
        "405",
        second,
        enabled=True,
    ) is True

    assert producer.evolve_calls == 1
    assert checker_calls == [first]
    assert executor.checked_request_response_pairs == {
        ("CONNECT", "405", "d" * 64)
    }
    updated = json.loads(record_path.read_text(encoding="utf-8"))
    assert updated["response_observation"] == "d" * 64


def test_observer_does_not_evolve_for_semantically_different_responses():
    executor, producer = make_executor("non_compliant")
    first = b"HTTP/1.1 405 Method Not Allowed\r\n\r\n"
    second = b"HTTP/1.1 405 Retry Later\r\nRetry-After: 30\r\n\r\n"
    executor.observer_funcs = {
        "405": lambda response: __import__("hashlib").sha256(
            response
        ).hexdigest()
    }
    producer.observers = {"405": [object()]}
    producer.responses_semantically_equivalent = lambda **kwargs: False
    producer.evolve_calls = 0
    producer.evolve_observer = (
        lambda **kwargs:
        setattr(producer, "evolve_calls", producer.evolve_calls + 1)
    )
    executor.checked_response_samples[
        ("CONNECT", "405", __import__("hashlib").sha256(first).hexdigest())
    ] = first

    digest = executor.observe_response_with_evolution("405", second)

    assert digest == __import__("hashlib").sha256(second).hexdigest()
    assert producer.evolve_calls == 0


class FakeChater:
    async def llm_checker_evolve(self, **kwargs):
        response = kwargs["response"]
        return (
            "def packet_checker(candidate: bytes) -> bool:\n"
            f"    return isinstance(candidate, bytes) and candidate == {response!r}\n"
        )

    async def llm_observer_evolve(self, **kwargs):
        return (
            "def packet_observer(response: bytes) -> str:\n"
            "    return 'e' * 64\n"
        )

    async def llm_observer_semantic_compare(self, **kwargs):
        return json.dumps({
            "semantic_equivalent": True,
            "confidence": 0.98,
            "reason": "Only the Date field changed.",
            "dynamic_differences": ["Date"],
            "behavioral_differences": [],
        })


def test_checker_evolution_persists_new_version(tmp_path: Path):
    checker_dir = tmp_path / "checkers" / "200"
    checker_dir.mkdir(parents=True)
    old_path = checker_dir / "id0.py"
    old_path.write_text(
        "def packet_checker(response: bytes) -> bool:\n"
        "    return False\n",
        encoding="utf-8",
    )

    producer = AsyncProducer.__new__(AsyncProducer)
    producer.chater = FakeChater()
    producer.rfcp = SimpleNamespace(pro_name="demo")
    producer.checker_path = tmp_path / "checkers"
    producer.checker_info_path = producer.checker_path / "checker_info.json"
    producer.checkers = {
        "200": [
            Checker(
                msg_type="200",
                evolved_from="init",
                name="id0",
                path=str(old_path),
                state_field="status",
            )
        ]
    }

    evolved = producer.evolve_checker(
        response_type="200",
        response=b"200 OK\r\n",
        analysis={"verdict": "compliant", "summary": "allowed"},
    )

    assert evolved is not None
    assert evolved.name == "id1"
    assert evolved.evolved_from == "id0"
    namespace = {}
    exec((checker_dir / "id1.py").read_text(encoding="utf-8"), namespace)
    assert namespace["packet_checker"](b"200 OK\r\n") is True

    metadata = json.loads(
        producer.checker_info_path.read_text(encoding="utf-8")
    )
    assert [item["name"] for item in metadata["200"]] == ["id0", "id1"]


def test_observer_evolution_persists_new_version(tmp_path: Path):
    observer_dir = tmp_path / "observers" / "405"
    observer_dir.mkdir(parents=True)
    old_path = observer_dir / "id0.py"
    old_path.write_text(
        "import hashlib\n"
        "def packet_observer(response: bytes) -> str:\n"
        "    return hashlib.sha256(response).hexdigest()\n",
        encoding="utf-8",
    )

    producer = AsyncProducer.__new__(AsyncProducer)
    producer.chater = FakeChater()
    producer.rfcp = SimpleNamespace(pro_name="http")
    producer.observer_path = tmp_path / "observers"
    producer.observer_info_path = producer.observer_path / "observer_info.json"
    producer.res_ir = etree.fromstring(
        b"<ir><message name='405'><field name='Date'/></message></ir>"
    )
    producer.observers = {
        "405": [
            ResponseObserver(
                msg_type="405",
                name="id0",
                path=str(old_path),
                state_field="StatusCode",
            )
        ]
    }

    evolved = producer.evolve_observer(
        response_type="405",
        samples=[
            b"HTTP/1.1 405\r\nDate: first\r\n\r\n",
            b"HTTP/1.1 405\r\nDate: second\r\n\r\n",
        ],
    )

    assert evolved is not None
    assert evolved.name == "id1"
    assert evolved.evolved_from == "id0"
    assert len(evolved.sample_observations) == 2
    metadata = json.loads(
        producer.observer_info_path.read_text(encoding="utf-8")
    )
    assert [item["name"] for item in metadata["405"]] == ["id0", "id1"]


def test_observer_semantic_comparison_uses_ir(tmp_path: Path):
    producer = AsyncProducer.__new__(AsyncProducer)
    producer.chater = FakeChater()
    producer.rfcp = SimpleNamespace(pro_name="http")
    producer.res_ir = etree.fromstring(
        b"<ir><message name='405'><field name='Date'/></message></ir>"
    )

    assert producer.responses_semantically_equivalent(
        response_type="405",
        old_response=b"HTTP/1.1 405\r\nDate: first\r\n\r\n",
        new_response=b"HTTP/1.1 405\r\nDate: second\r\n\r\n",
    ) is True


def test_low_confidence_semantic_match_does_not_allow_evolution():
    class LowConfidenceChater(FakeChater):
        async def llm_observer_semantic_compare(self, **kwargs):
            return json.dumps({
                "semantic_equivalent": True,
                "confidence": 0.5,
                "reason": "The available evidence is ambiguous.",
                "dynamic_differences": [],
                "behavioral_differences": [],
            })

    producer = AsyncProducer.__new__(AsyncProducer)
    producer.chater = LowConfidenceChater()
    producer.rfcp = SimpleNamespace(pro_name="http")
    producer.res_ir = etree.fromstring(
        b"<ir><message name='405'><field name='Date'/></message></ir>"
    )

    assert producer.responses_semantically_equivalent(
        response_type="405",
        old_response=b"HTTP/1.1 405\r\nDate: first\r\n\r\n",
        new_response=b"HTTP/1.1 405\r\nDate: second\r\n\r\n",
    ) is False
