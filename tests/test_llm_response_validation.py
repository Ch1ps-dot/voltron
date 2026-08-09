import asyncio
import csv
import json
from types import SimpleNamespace

import pytest

from voltron.analyzer.analyzer import Analyzer, analyzer
from voltron.configs import configs
from voltron.llm.chatter import (
    AsyncChater,
    CandidateSourceValidationError,
)
from voltron.llm.incremental import content_sha256
from voltron.llm.response_validation import (
    LLMResponseValidationError,
    ResponseContract,
    response_contract_for_usage,
    validate_response,
)


@pytest.mark.parametrize("response", [None, "", " \n\t"])
def test_response_validation_rejects_empty_content(response):
    with pytest.raises(LLMResponseValidationError) as failure:
        validate_response(response, ResponseContract())

    assert failure.value.reason == "empty_response"


def test_python_response_requires_complete_artifact_and_function():
    contract = ResponseContract(
        kind="python",
        required_function="generate",
    )
    fenced = "```python\ndef generate():\n    return b'PING'\n```"

    result = validate_response(fenced, contract)

    assert result.normalized.startswith("def generate")

    with pytest.raises(LLMResponseValidationError) as prose_failure:
        validate_response(f"Here is the code:\n{fenced}", contract)
    assert prose_failure.value.reason == "artifact_with_prose"

    with pytest.raises(LLMResponseValidationError) as function_failure:
        validate_response("value = 1", contract)
    assert function_failure.value.reason == "missing_function"


def test_json_response_must_be_complete_and_match_usage_schema():
    contract = response_contract_for_usage("possible_res")
    response = '```json\n{"possible_response":["200"]}\n```'

    result = validate_response(response, contract)

    assert result.parsed == {"possible_response": ["200"]}

    with pytest.raises(LLMResponseValidationError) as trailing_failure:
        validate_response('{"possible_response":[]} trailing', contract)
    assert trailing_failure.value.reason == "invalid_json"

    with pytest.raises(LLMResponseValidationError) as schema_failure:
        validate_response('{"possible_response":"200"}', contract)
    assert schema_failure.value.reason == "schema_failure"


def test_xml_response_checks_root_and_expected_message():
    contract = ResponseContract(
        kind="xml",
        allowed_xml_roots=frozenset({"message"}),
        expected_message="PING",
    )

    validated = validate_response(
        '```xml\n<message name="PING"/>\n```',
        contract,
    )

    assert validated.parsed.tag == "message"

    with pytest.raises(LLMResponseValidationError) as root_failure:
        validate_response("<field name=\"Code\"/>", contract)
    assert root_failure.value.reason == "invalid_xml_root"

    with pytest.raises(LLMResponseValidationError) as message_failure:
        validate_response("<message name=\"PONG\"/>", contract)
    assert message_failure.value.reason == "missing_message"


def test_source_delta_validation_is_followed_by_required_function_check():
    source = "def generate():\n    return b'PING'\n"
    delta = json.dumps({
        "base_sha256": content_sha256(source),
        "edits": [{
            "start_line": 1,
            "end_line": 2,
            "replacement": "value = 1",
        }],
    })

    with pytest.raises(CandidateSourceValidationError) as failure:
        AsyncChater._apply_python_delta(source, delta, "generate")

    assert failure.value.reason == "missing_function"
    assert failure.value.candidate_source == "value = 1\n"


def test_source_delta_no_change_keeps_a_generator_baseline():
    source = "def generate():\n    return b'PING'\n"
    delta = json.dumps({
        "base_sha256": content_sha256(source),
        "action": "no_change",
        "reason": "no_safe_change",
        "edits": [],
    })

    result = AsyncChater._apply_python_delta(source, delta, "mutate")

    assert result == source
    assert result.changed is False


def test_source_delta_invalid_python_exposes_candidate_for_repair():
    source = "def generate():\n    return b'PING'\n"
    delta = json.dumps({
        "base_sha256": content_sha256(source),
        "edits": [{
            "start_line": 1,
            "end_line": 2,
            "replacement": "def mutate(:\n",
        }],
    })

    with pytest.raises(CandidateSourceValidationError) as failure:
        AsyncChater._apply_python_delta(source, delta, "mutate")

    assert failure.value.reason == "invalid_python"
    assert failure.value.candidate_source == "def mutate(:\n"


def test_source_delta_no_change_requires_an_allowed_reason_and_empty_edits():
    contract = ResponseContract(kind="source_delta")
    valid = {
        "base_sha256": "a" * 64,
        "action": "no_change",
        "reason": "no_safe_change",
        "edits": [],
    }
    assert validate_response(json.dumps(valid), contract).parsed == valid

    invalid = dict(valid, edits=[{
        "start_line": 1,
        "end_line": 1,
        "replacement": "pass",
    }])
    with pytest.raises(LLMResponseValidationError, match="no_change requires"):
        validate_response(json.dumps(invalid), contract)


def _completion(content, *, finish_reason=None, completion_tokens=4):
    return SimpleNamespace(
        choices=[SimpleNamespace(
            message=SimpleNamespace(content=content),
            finish_reason=finish_reason,
        )],
        usage=SimpleNamespace(
            prompt_tokens=6,
            completion_tokens=completion_tokens,
            total_tokens=6 + completion_tokens,
        ),
    )


def test_chat_llm_rejects_blank_response_and_records_failure(monkeypatch):
    recorded = {}

    async def create(**_kwargs):
        return _completion("   ", completion_tokens=3)

    chatter = AsyncChater.__new__(AsyncChater)
    chatter.clt = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    )
    chatter.model = "test-model"
    monkeypatch.setattr(chatter, "_remaining_fuzz_time_s", lambda: None)
    monkeypatch.setattr(
        analyzer,
        "record_llm_usage",
        lambda **kwargs: recorded.update(kwargs),
    )

    with pytest.raises(LLMResponseValidationError) as failure:
        asyncio.run(chatter.chat_llm("TASK", "generator_gen"))

    assert failure.value.reason == "empty_response"
    assert recorded["response_valid"] is False
    assert recorded["validation_reason"] == "empty_response"
    assert recorded["completion_tokens"] == 3


def test_chat_llm_normalizes_valid_fenced_code(monkeypatch):
    recorded = {}

    async def create(**_kwargs):
        return _completion(
            "```python\ndef generate():\n    return b'PING'\n```"
        )

    chatter = AsyncChater.__new__(AsyncChater)
    chatter.clt = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    )
    chatter.model = "test-model"
    monkeypatch.setattr(chatter, "_remaining_fuzz_time_s", lambda: None)
    monkeypatch.setattr(
        analyzer,
        "record_llm_usage",
        lambda **kwargs: recorded.update(kwargs),
    )

    response = asyncio.run(chatter.chat_llm("TASK", "generator_gen"))

    assert response == "def generate():\n    return b'PING'"
    assert recorded["response_valid"] is True
    assert recorded["response_contract"] == "python"


def test_chat_llm_rejects_truncated_completion(monkeypatch):
    recorded = {}

    async def create(**_kwargs):
        return _completion('{"possible_response":[', finish_reason="length")

    chatter = AsyncChater.__new__(AsyncChater)
    chatter.clt = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    )
    chatter.model = "test-model"
    monkeypatch.setattr(chatter, "_remaining_fuzz_time_s", lambda: None)
    monkeypatch.setattr(
        analyzer,
        "record_llm_usage",
        lambda **kwargs: recorded.update(kwargs),
    )

    with pytest.raises(LLMResponseValidationError) as failure:
        asyncio.run(chatter.chat_llm("TASK", "possible_res"))

    assert failure.value.reason == "truncated_response"
    assert recorded["validation_reason"] == "truncated_response"


def test_validation_metrics_count_discarded_tokens_without_raw_response(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(configs, "results_path", tmp_path, raising=False)
    metric = Analyzer()
    metric.reset_phase_metrics()

    metric.record_llm_usage(
        duration_s=0.2,
        prompt_tokens=10,
        completion_tokens=7,
        total_tokens=17,
        usage="generator_gen",
        model="model-a",
        response_valid=False,
        validation_reason="invalid_python",
        response_contract="python",
        response_chars=42,
        response_sha256="a" * 64,
    )

    with (tmp_path / "llm_usage_metrics.csv").open(
        encoding="utf-8",
        newline="",
    ) as stream:
        row = next(csv.DictReader(stream))
    assert row["invalid_responses"] == "1"
    assert row["schema_failures"] == "1"
    assert row["discarded_completion_tokens"] == "7"

    event = json.loads(
        (tmp_path / "llm_response_validation.jsonl").read_text(
            encoding="utf-8"
        )
    )
    assert event["status"] == "invalid"
    assert event["reason"] == "invalid_python"
    assert event["response_sha256"] == "a" * 64
    assert "response" not in event
