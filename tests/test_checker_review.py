import json
import threading
from pathlib import Path
from types import SimpleNamespace

from voltron.configs import configs
from voltron.executor.conversation import Conversation
from voltron.executor.executor import Executor
from voltron.synthesizer.checker import Checker
from voltron.synthesizer.synthesizer import AsyncProducer


class FakeProducer:
    def __init__(self, verdict: str) -> None:
        self.verdict = verdict
        self.review_calls = 0
        self.evolve_calls = 0

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
    executor._invalid_response_lock = threading.Lock()
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


class FakeChater:
    async def llm_checker_evolve(self, **kwargs):
        response = kwargs["response"]
        return (
            "def packet_checker(candidate: bytes) -> bool:\n"
            f"    return isinstance(candidate, bytes) and candidate == {response!r}\n"
        )


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
