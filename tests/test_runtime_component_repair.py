import json
import threading
from types import SimpleNamespace

import pytest

import voltron.fuzz as fuzz_module
from voltron.analyzer.analyzer import analyzer
from voltron.configs import configs
from voltron.executor.executor import Executor
from voltron.executor.mapper import Mapper
from voltron.fuzz import Fuzzer, NoCoverageInputError
from voltron.synthesizer.parser import Parser
from voltron.synthesizer.code_validation import validate_generated_code
from voltron.synthesizer.synthesizer import AsyncProducer


def test_parser_contract_rejects_string_regex_and_non_bytes_results():
    string_regex = (
        "import re\n"
        "def packet_parser(response):\n"
        "    match = re.match(r'^(\\d{3})', response)\n"
        "    return match.group(1) if match else None\n"
    )
    result = validate_generated_code(
        string_regex,
        "packet_parser",
        "parser",
    )

    assert result.ok is False
    assert "bytes-like object" in result.error


def test_parser_runtime_failure_repairs_and_replays_same_response():
    banner = b"220 ProFTPD Server ready\r\n"
    repaired_code = (
        "import re\n"
        "def packet_parser(response):\n"
        "    match = re.match(br'^(\\d{3})', response)\n"
        "    return match.group(1) if match else b''\n"
    )
    repairs = []
    replacement = SimpleNamespace(name="id1")

    class FakeMapper:
        cur_parser = SimpleNamespace(name="id0")

        def repair_runtime_component(self, **kwargs):
            repairs.append(kwargs)
            return replacement, repaired_code

    executor = Executor.__new__(Executor)
    executor.mapper = FakeMapper()
    executor.parser_func = lambda response: __import__("re").match(
        r"^(\d{3})", response
    )
    executor._parser_code = (
        "import re\ndef packet_parser(response):\n"
        "    return re.match(r'^(\\d{3})', response)\n"
    )
    executor._parser_version = "id0"
    executor._last_known_good_parser = None
    executor.analyzer = SimpleNamespace(
        lock=threading.Lock(), current_operation=""
    )

    def load_parser(parser):
        namespace = {}
        exec(repaired_code, namespace)
        executor.parser_func = namespace["packet_parser"]
        executor._parser_code = repaired_code
        executor._parser_version = parser.name

    executor.load_parser = load_parser

    assert executor._parse_tcp_response(banner, "-", False) == "220"
    assert len(repairs) == 1
    assert repairs[0]["runtime_input"] == banner
    assert executor._parser_version == "id1"


def test_parser_runtime_failure_degrades_to_parse_failure_after_repair_exhaustion():
    response = b"\xff\xfebinary-response"
    repairs = []

    class FakeMapper:
        cur_parser = SimpleNamespace(name="id0")

        def repair_runtime_component(self, **kwargs):
            repairs.append(kwargs)
            return None

    executor = Executor.__new__(Executor)
    executor.mapper = FakeMapper()
    executor.parser_func = lambda _response: b""
    executor._parser_code = "def packet_parser(_response): return b''\n"
    executor._parser_version = "id0"
    executor._last_known_good_parser = None
    executor.parser_degraded = False
    executor.parser_fallback_count = 0

    assert executor._parse_tcp_response(response, "-", False) == "PARSE_FAILURE"
    assert len(repairs) == 1
    assert repairs[0]["runtime_input"] == response
    assert executor.parser_degraded is True
    assert executor.parser_fallback_count == 1


def test_parser_validation_rejects_empty_explicit_runtime_sample():
    result = validate_generated_code(
        "def packet_parser(_response):\n    return b''\n",
        "packet_parser",
        "parser",
        runtime_samples=(b"220 service ready\r\n",),
        require_nonempty_samples=True,
    )

    assert result.ok is False
    assert "could not classify runtime sample" in result.error


def test_runtime_repair_is_deduplicated_and_records_artifacts(
    tmp_path,
    monkeypatch,
):
    calls = []
    replacement = SimpleNamespace(name="id1")

    class FakeProducer:
        def repair_runtime_component(self, **kwargs):
            calls.append(kwargs)
            return replacement, "def generate():\n    return b'PING'\n"

    mapper = Mapper.__new__(Mapper)
    mapper.producer = FakeProducer()
    monkeypatch.setattr(configs, "results_path", tmp_path, raising=False)
    monkeypatch.setattr(analyzer, "stage", "model learning", raising=False)

    kwargs = {
        "component": "generator",
        "component_type": "PING",
        "version": "id0",
        "source_code": "def generate():\n    raise RuntimeError('bad')\n",
        "error": "RuntimeError: bad",
    }
    first = mapper.repair_runtime_component(**kwargs)
    second = mapper.repair_runtime_component(**kwargs)

    assert first == second
    assert len(calls) == 1
    failures = [
        json.loads(line)
        for line in (tmp_path / "component_runtime_failures.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    repairs = [
        json.loads(line)
        for line in (tmp_path / "component_repairs.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert len(failures) == 2
    assert len(repairs) == 1
    assert repairs[0]["status"] == "published"


def test_runtime_parser_repair_rejects_invalid_candidate_then_publishes(
    tmp_path,
    monkeypatch,
):
    class RepairingChater:
        def __init__(self):
            self.calls = 0

        async def llm_code_repair(self, **_kwargs):
            self.calls += 1
            if self.calls == 1:
                return "def packet_parser(_response):\n    return '220'\n"
            return "def packet_parser(_response):\n    return b'220'\n"

    producer = AsyncProducer.__new__(AsyncProducer)
    producer.chater = RepairingChater()
    producer.rfcp = SimpleNamespace(
        res_type_rules={"primary_fields": ["status_code"]},
        res_json=[{"field_name": "status_code"}],
    )
    producer.parser_path = tmp_path / "parsers"
    producer.parser_info_path = producer.parser_path / "parser_info.json"
    producer.generation_manifest_path = tmp_path / "generation_manifest.jsonl"
    producer.parsers = [
        Parser(evolved_from="init", name="id0", state_field="status_code")
    ]
    monkeypatch.setattr(configs, "results_path", tmp_path, raising=False)
    monkeypatch.setattr(configs, "generation_retry_limit", 3, raising=False)

    result = producer.repair_runtime_component(
        component="parser",
        component_type="__all__",
        source_code="def packet_parser(_response):\n    return None\n",
        error="TypeError: parser returned None",
        runtime_input=b"220 ProFTPD ready\r\n",
    )

    assert result is not None
    metadata, code = result
    assert producer.chater.calls == 2
    assert metadata.name == "id1"
    assert code.endswith("return b'220'\n")
    assert (producer.parser_path / "id1.py").read_text(
        encoding="utf-8"
    ) == code


def test_fuzz_worker_failure_propagates_to_caller(monkeypatch):
    fuzzer = Fuzzer.__new__(Fuzzer)
    fuzzer.stop_event = threading.Event()
    fuzzer._worker_threads = []
    fuzzer._install_signal_handlers = lambda: None
    fuzzer.cleanup = lambda: None

    def fail_worker(_stop_event):
        raise ValueError("worker broke")

    fuzzer.state_fuzz = fail_worker
    monkeypatch.setattr(
        fuzz_module,
        "ui_loop",
        lambda stop_event: stop_event.wait(timeout=1),
    )

    with pytest.raises(RuntimeError, match="voltron-fuzz worker failed"):
        fuzzer.fuzz("state", 1)


def test_empty_replay_is_reported_as_no_coverage_input(
    tmp_path,
    monkeypatch,
):
    result_dir = tmp_path / "results"
    (result_dir / "replayable_testcases").mkdir(parents=True)
    fuzzer = Fuzzer.__new__(Fuzzer)
    fuzzer.exe = SimpleNamespace()
    fuzzer.stop_event = threading.Event()
    monkeypatch.setattr(configs, "target_name", "demo", raising=False)

    with pytest.raises(NoCoverageInputError):
        fuzzer.replay_process(result_dir, tmp_path / "coverage")

    status = json.loads(
        (result_dir / "coverage_replay_status.json").read_text(
            encoding="utf-8"
        )
    )
    assert status["status"] == "NO_COVERAGE_INPUT"
    assert status["valid_testcase_count"] == 0
