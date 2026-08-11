import asyncio
import json
from pathlib import Path
from string import Template
from types import SimpleNamespace

import pytest
from lxml import etree

from voltron.llm.chatter import AsyncChater
from voltron.llm.incremental import (
    IncrementalOutputError,
    SourceDeltaResult,
    apply_ir_delta,
    apply_source_delta,
    content_sha256,
    numbered_source_context,
)


ROOT = Path(__file__).resolve().parents[1]


def test_source_delta_applies_non_overlapping_line_replacements():
    source = (
        "def generate():\n"
        "    value = b'A'\n"
        "    return value\n"
    )
    delta = {
        "base_sha256": content_sha256(source),
        "edits": [
            {
                "start_line": 2,
                "end_line": 2,
                "replacement": "    value = b'B'",
            },
            {
                "start_line": 3,
                "end_line": 3,
                "replacement": "    return value + b'!'",
            },
        ],
    }

    evolved = apply_source_delta(source, delta)

    assert isinstance(evolved, SourceDeltaResult)
    assert evolved.changed is True
    assert evolved == (
        "def generate():\n"
        "    value = b'B'\n"
        "    return value + b'!'\n"
    )


@pytest.mark.parametrize(
    "delta",
    [
        {
            "base_sha256": "wrong",
            "edits": [
                {"start_line": 1, "end_line": 1, "replacement": "pass"}
            ],
        },
        {
            "base_sha256": content_sha256("a\nb\n"),
            "edits": [
                {"start_line": 1, "end_line": 2, "replacement": "a"},
                {"start_line": 2, "end_line": 2, "replacement": "b"},
            ],
        },
    ],
)
def test_source_delta_rejects_wrong_baseline_or_overlaps(delta):
    with pytest.raises(IncrementalOutputError):
        apply_source_delta("a\nb\n", delta)


def test_source_delta_can_explicitly_keep_the_matching_baseline():
    source = "def generate():\n    return b'PING'\n"
    delta = {
        "base_sha256": content_sha256(source),
        "action": "no_change",
        "reason": "insufficient_evidence",
        "edits": [],
    }

    evolved = apply_source_delta(source, delta)

    assert evolved == source
    assert evolved.changed is False
    assert evolved.reason == "insufficient_evidence"


@pytest.mark.parametrize(
    "delta",
    [
        {
            "base_sha256": content_sha256("x\n"),
            "action": "no_change",
            "reason": "insufficient_evidence",
            "edits": [{"start_line": 1, "end_line": 1, "replacement": "y"}],
        },
        {
            "base_sha256": content_sha256("x\n"),
            "action": "no_change",
            "reason": "unsupported",
            "edits": [],
        },
    ],
)
def test_source_delta_rejects_invalid_no_change(delta):
    with pytest.raises(IncrementalOutputError):
        apply_source_delta("x\n", delta)


def test_numbered_source_context_preserves_real_line_numbers_when_compacted():
    source = "\n".join(f"line_{index}_{'x' * 80}" for index in range(100))

    context = numbered_source_context(source, max_chars=512)

    assert "1|line_0_" in context
    assert "100|line_99_" in context
    assert "omitted source lines" in context
    assert len(context) <= 512


def test_numbered_source_context_bounds_a_single_very_long_line():
    context = numbered_source_context("value = '" + ("x" * 10_000) + "'", 512)

    assert len(context) <= 512
    assert "1|value = '" in context
    assert "line truncated" in context


def test_ir_delta_updates_and_reorders_fields_without_repeating_xml():
    source = (
        '<message name="M">'
        '<field name="A" type="constant" length="1B" value="A"/>'
        '<!-- old A -->'
        '<field name="B" type="variable" length="1B" value="ASCII"/>'
        '</message>'
    )
    delta = {
        "base_sha256": content_sha256(source),
        "ops": [
            {
                "op": "update_field",
                "message": "M",
                "field": "A",
                "set": {"value": "Z"},
                "remove": [],
            },
            {
                "op": "insert_field",
                "message": "M",
                "index": 1,
                "attributes": {
                    "name": "C",
                    "type": "constant",
                    "length": "1B",
                    "value": "C",
                },
                "note": "new C",
            },
            {"op": "move_field", "message": "M", "field": "B", "index": 0},
            {
                "op": "set_field_note",
                "message": "M",
                "field": "A",
                "note": "updated A",
            },
        ],
    }

    evolved = apply_ir_delta(source, delta)
    root = etree.fromstring(evolved.encode("utf-8"))

    assert [field.get("name") for field in root.findall("field")] == [
        "B",
        "A",
        "C",
    ]
    assert root.findall("field")[1].get("value") == "Z"
    assert "updated A" in evolved
    assert "new C" in evolved


def test_ir_delta_can_insert_a_complete_message():
    source = (
        '<ir><message name="A"><field name="Code" type="constant" '
        'length="1B" value="A"/></message></ir>'
    )
    delta = {
        "base_sha256": content_sha256(source),
        "ops": [
            {
                "op": "insert_message",
                "index": 1,
                "value": {
                    "attributes": {"name": "B"},
                    "note": "message B",
                    "fields": [
                        {
                            "attributes": {
                                "name": "Code",
                                "type": "constant",
                                "length": "1B",
                                "value": "B",
                            },
                            "note": "code B",
                        }
                    ],
                },
            }
        ],
    }

    evolved = apply_ir_delta(source, delta)
    root = etree.fromstring(evolved.encode("utf-8"))

    assert [message.get("name") for message in root.findall("message")] == [
        "A",
        "B",
    ]


def test_incremental_outputs_are_smaller_for_realistic_evolve_inputs():
    source = "\n".join(
        ["def generate():", "    message = bytearray()"]
        + [f"    field_{index} = b'VALUE_{index:03d}'" for index in range(120)]
        + ["    return bytes(message)", ""]
    )
    delta = {
        "base_sha256": content_sha256(source),
        "edits": [
            {
                "start_line": 62,
                "end_line": 62,
                "replacement": "    field_59 = b'BOUNDARY_VALUE'",
            }
        ],
    }
    encoded_delta = json.dumps(delta, separators=(",", ":"))

    evolved = apply_source_delta(source, delta)

    assert "BOUNDARY_VALUE" in evolved
    assert len(encoded_delta) < len(evolved) * 0.1


@pytest.mark.parametrize(
    ("template_name", "template_path", "method_name", "kwargs", "source_key", "replacement", "expected"),
    [
        (
            "_tem_generator_evolve",
            "skills/evolver/generator_evolve.md",
            "llm_generator_evolve",
            {
                "pro_name": "demo",
                "field_name": "method",
                "msg_type": "PING",
                "code": "def generate():\n    return b'A'\n",
                "msg_ir": "<message />",
                "info": "sut",
                "trace": "trace",
                "related_code": "",
            },
            "code",
            "    return b'B'",
            "def generate():\n    return b'B'\n",
        ),
        (
            "_tem_parser_evolve",
            "skills/evolver/parser_evolve.md",
            "llm_parser_evolve",
            {
                "pro_name": "demo",
                "res_info": "[]",
                "old_code": "def packet_parser(response: bytes):\n    return b''\n",
                "message": b"200 OK",
                "type_rules": "{}",
            },
            "old_code",
            "    return b'200'",
            "def packet_parser(response: bytes):\n    return b'200'\n",
        ),
        (
            "_tem_mutator_evolve",
            "skills/evolver/generator_mutate.md",
            "llm_mutator_evolve",
            {
                "pro_name": "demo",
                "field_name": "method",
                "msg_type": "PING",
                "code": "def generate():\n    return b'A'\n",
                "msg_ir": "<message />",
                "info": "sut",
                "poss_response": "PONG",
                "trace": "[]",
            },
            "code",
            "def mutate():\n    return b'M'",
            "def mutate():\n    return b'M'\n",
        ),
        (
            "_tem_observer_evolve",
            "skills/evolver/observer_evolve.md",
            "llm_observer_evolve",
            {
                "pro_name": "demo",
                "response_type": "200",
                "msg_ir": "<message />",
                "original_code": (
                    "def packet_observer(response: bytes):\n"
                    "    return 'a' * 64\n"
                ),
                "samples": "[]",
            },
            "original_code",
            "    return 'b' * 64",
            "def packet_observer(response: bytes):\n    return 'b' * 64\n",
        ),
        (
            "_tem_checker_evolve",
            "skills/evolver/checker_evolve.md",
            "llm_checker_evolve",
            {
                "pro_name": "demo",
                "response_type": "200",
                "original_code": (
                    "def packet_checker(response: bytes):\n"
                    "    return False\n"
                ),
                "response": b"200 OK",
                "review_summary": "allowed",
            },
            "original_code",
            "    return True",
            "def packet_checker(response: bytes):\n    return True\n",
        ),
    ],
)
def test_python_evolve_methods_apply_model_delta(
    template_name,
    template_path,
    method_name,
    kwargs,
    source_key,
    replacement,
    expected,
):
    template = Template((ROOT / template_path).read_text(encoding="utf-8"))
    chatter = AsyncChater.__new__(AsyncChater)
    chatter.pmp = SimpleNamespace(**{template_name: template})
    source = kwargs[source_key]
    captured = {}

    async def fake_chat_llm(prompt, usage):
        captured["prompt"] = prompt
        captured["usage"] = usage
        end_line = 2
        start_line = 1 if method_name == "llm_mutator_evolve" else 2
        return json.dumps({
            "base_sha256": content_sha256(source),
            "edits": [
                {
                    "start_line": start_line,
                    "end_line": end_line,
                    "replacement": replacement,
                }
            ],
        })

    chatter.chat_llm = fake_chat_llm

    result = asyncio.run(getattr(chatter, method_name)(**kwargs))

    assert result == expected
    assert result.changed is True
    assert content_sha256(source) in captured["prompt"]
    assert "1|" in captured["prompt"]
    assert "edits" in captured["prompt"]
    function_names = {
        "llm_generator_evolve": "generate",
        "llm_parser_evolve": "packet_parser",
        "llm_mutator_evolve": "mutate",
        "llm_observer_evolve": "packet_observer",
        "llm_checker_evolve": "packet_checker",
    }
    namespace = {}
    exec(result, namespace)
    assert callable(namespace[function_names[method_name]])


def test_python_evolve_methods_preserve_a_valid_no_change_result():
    template = Template(
        (ROOT / "skills/evolver/generator_evolve.md").read_text(encoding="utf-8")
    )
    chatter = AsyncChater.__new__(AsyncChater)
    chatter.pmp = SimpleNamespace(_tem_generator_evolve=template)
    source = "def generate():\n    return b'A'\n"

    async def fake_chat_llm(*, prompt, usage):
        assert prompt
        assert usage == "generator_evolve"
        return json.dumps({
            "base_sha256": content_sha256(source),
            "action": "no_change",
            "reason": "already_satisfies_goal",
            "edits": [],
        })

    chatter.chat_llm = fake_chat_llm

    result = asyncio.run(chatter.llm_generator_evolve(
        pro_name="demo",
        field_name="method",
        msg_type="PING",
        code=source,
        msg_ir="<message />",
        info="sut",
        trace="",
        related_code="",
    ))

    assert result == source
    assert result.changed is False
    assert result.reason == "already_satisfies_goal"


def test_all_source_evolve_prompts_describe_the_no_change_result():
    for path in (
        "skills/evolver/generator_evolve.md",
        "skills/evolver/parser_evolve.md",
        "skills/evolver/generator_mutate.md",
        "skills/evolver/observer_evolve.md",
        "skills/evolver/checker_evolve.md",
    ):
        prompt = (ROOT / path).read_text(encoding="utf-8")
        assert '"action":"no_change"' in prompt
        assert '"reason"' in prompt


def test_generator_evolve_and_mutate_prompts_allow_info_resource_paths():
    evolve_prompt = (ROOT / "skills/evolver/generator_evolve.md").read_text(
        encoding="utf-8"
    )
    mutate_prompt = (ROOT / "skills/evolver/generator_mutate.md").read_text(
        encoding="utf-8"
    )

    assert "Use target-specific URLs or named resources stated in SUT_CONTEXT" in evolve_prompt
    assert "You may use target-specific URLs or named resources stated in SUT_CONTEXT" in mutate_prompt


def test_generator_evolve_prompt_requires_context_credentials_for_auth_requests():
    evolve_prompt = (ROOT / "skills/evolver/generator_evolve.md").read_text(
        encoding="utf-8"
    )

    assert "When SUT_CONTEXT contains account credentials" in evolve_prompt
    assert "every authentication-related request type must use those exact credentials" in evolve_prompt
    assert "Do not invent, alter, or apply credentials to unrelated request types" in evolve_prompt


def test_generator_and_mutator_prompts_require_one_message_of_the_requested_type():
    prompt_paths = (
        "skills/builder/generator_generation.md",
        "skills/evolver/generator_evolve.md",
        "skills/evolver/generator_mutate.md",
    )

    for path in prompt_paths:
        prompt = (ROOT / path).read_text(encoding="utf-8")
        assert "exactly one complete `$msg_type` request" in prompt
        assert "Do not concatenate messages" in prompt
        assert "multi-message sequence" in prompt


def test_ir_evolve_method_applies_ops_and_returns_xml():
    template = Template(
        (ROOT / "skills/evolver/ir_evolve.md").read_text(encoding="utf-8")
    )
    chatter = AsyncChater.__new__(AsyncChater)
    chatter.pmp = SimpleNamespace(_tem_ir_evolve=template)
    source = (
        '<message name="PING"><field name="Code" type="constant" '
        'length="4B" value="PING"/></message>'
    )

    async def fake_chat_llm(prompt, usage):
        assert content_sha256(source) in prompt
        assert usage == "ir_evolve"
        return json.dumps({
            "base_sha256": content_sha256(source),
            "ops": [
                {
                    "op": "update_field",
                    "message": "PING",
                    "field": "Code",
                    "set": {"length": "5B"},
                    "remove": [],
                }
            ],
        })

    chatter.chat_llm = fake_chat_llm

    evolved = asyncio.run(
        chatter.llm_ir_evolve(
            pro_name="demo",
            direction="request",
            msg_type="PING",
            current_ir=source,
            type_rule="{}",
            section_context="spec",
            feedback="length mismatch",
        )
    )

    root = etree.fromstring(evolved.encode("utf-8"))
    assert root.find("field").get("length") == "5B"


def test_ir_evolve_method_rejects_invalid_delta_without_replacing_ir():
    template = Template(
        (ROOT / "skills/evolver/ir_evolve.md").read_text(encoding="utf-8")
    )
    chatter = AsyncChater.__new__(AsyncChater)
    chatter.pmp = SimpleNamespace(_tem_ir_evolve=template)

    async def fake_chat_llm(prompt, usage):
        return '{"base_sha256":"wrong","ops":[]}'

    chatter.chat_llm = fake_chat_llm

    result = asyncio.run(
        chatter.llm_ir_evolve(
            pro_name="demo",
            direction="request",
            msg_type="PING",
            current_ir='<message name="PING"/>',
            type_rule="{}",
            section_context="spec",
            feedback="failure",
        )
    )

    assert result == ""
