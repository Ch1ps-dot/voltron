import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

from voltron.analyzer.analyzer import analyzer
from voltron.configs import configs
from voltron.llm.chatter import AsyncChater, SYSTEM_PROMPT


ROOT = Path(__file__).resolve().parents[1]


def test_xml_ir_is_compacted_to_loss_aware_field_table():
    source = """
    <ir version="1">
      <message name="PING">
        <!-- request purpose -->
        <field name="Code" type="constant" length="4B" value="PING"/>
        <!-- command code -->
        <field name="Arg" type="variable" length="undefined"
               value="ASCII" optional="true"/>
      </message>
    </ir>
    """

    encoded = AsyncChater._xml_ir_to_field_table(source)
    table = json.loads(encoded)

    assert "<field" not in encoded
    assert table["ir_attributes"] == {"version": "1"}
    assert table["columns"] == [
        "name",
        "type",
        "length",
        "value",
        "optional",
        "note",
    ]
    message = table["messages"][0]
    assert message["name"] == "PING"
    assert message["note"] == "request purpose"
    assert message["fields"] == [
        ["Code", "constant", "4B", "PING", None, "command code"],
        ["Arg", "variable", "undefined", "ASCII", "true", None],
    ]


def test_invalid_xml_ir_is_preserved_for_repair():
    malformed = '<message name="PING"><field name="Code"'
    assert AsyncChater._xml_ir_to_field_table(malformed) == malformed


def test_large_ir_keeps_valid_json_and_prioritizes_target(monkeypatch):
    fields = "".join(
        '<field name="F{index}" type="variable" length="undefined" '
        'value="{value}"/><!-- {note} -->'.format(
            index=index,
            value="x" * 600,
            note="n" * 600,
        )
        for index in range(8)
    )
    source = (
        '<ir><message name="HEAD"><field name="A" type="constant" '
        'length="1B" value="A"/></message>'
        f'<message name="TARGET">{fields}</message></ir>'
    )
    monkeypatch.setattr(configs, "prompt_context_max_chars", 512)

    encoded = AsyncChater._compact_ir_context(source, "TARGET")
    table = json.loads(encoded)

    assert len(encoded) <= 512
    assert [message["name"] for message in table["messages"]] == ["TARGET"]
    assert table["messages"][0]["fields"]
    assert table["messages"][0]["omitted_fields"] > 0


def test_every_prompt_is_structured_and_has_no_role_preamble():
    prompts = sorted((ROOT / "skills").rglob("*.md"))

    assert len(prompts) == 23
    for prompt in prompts:
        content = prompt.read_text(encoding="utf-8")
        assert content.startswith(("TASK\n", "SCOPE\n")), prompt
        assert "You are " not in content, prompt
        assert "OUTPUT\n" in content, prompt


def test_chat_uses_one_fixed_short_system_prompt(monkeypatch):
    captured = {}
    recorded = {}

    async def create(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))],
            usage=None,
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

    assert asyncio.run(chatter.chat_llm("TASK\nexample", "test")) == "ok"
    assert captured["messages"] == [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": "TASK\nexample"},
    ]
    assert len(SYSTEM_PROMPT) <= 80
    assert recorded["usage"] == "test"
    assert recorded["model"] == "test-model"
    assert recorded["tokens_reported"] is False
