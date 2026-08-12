import asyncio
from pathlib import Path
from string import Template
from types import SimpleNamespace

import pytest
import yaml

from voltron.configs import configs
from voltron.fuzz import decode_parser_validation_samples
from voltron.llm.chatter import AsyncChater
from voltron.synthesizer.synthesizer import AsyncProducer


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_decode_parser_validation_samples_supports_text_hex_and_base64():
    assert decode_parser_validation_samples(
        [
            "220 ready\r\n",
            {"hex": "5349502f322e3020323030204f4b0d0a0d0a"},
            {"base64": "UlRTUC8xLjAgMjAwIE9LDQoNCg=="},
            {"text": "220 ready\r\n"},
        ]
    ) == (
        b"220 ready\r\n",
        b"SIP/2.0 200 OK\r\n\r\n",
        b"RTSP/1.0 200 OK\r\n\r\n",
    )


@pytest.mark.parametrize(
    "samples",
    [
        "not-a-list",
        [""],
        [{"unknown": "value"}],
        [{"hex": "not-hex"}],
        [{"base64": "not-base64"}],
        [b"bytes-are-not-a-config-value"],
    ],
)
def test_decode_parser_validation_samples_rejects_invalid_config(samples):
    with pytest.raises((TypeError, ValueError)):
        decode_parser_validation_samples(samples)


def test_initial_parser_repair_receives_real_sample_and_expected_field(
    monkeypatch,
):
    sample = b"220 service ready\r\n"
    monkeypatch.setattr(
        configs,
        "parser_validation_samples",
        (sample,),
        raising=False,
    )

    class Chater:
        def __init__(self):
            self.repair_error = ""
            self.generation_kwargs = {}

        async def llm_parser_gen(self, **kwargs):
            self.generation_kwargs = kwargs
            return (
                "def packet_parser(response):\n"
                "    return b''\n"
            )

        async def llm_code_repair(self, **kwargs):
            self.repair_error = kwargs["error"]
            return (
                "def packet_parser(response):\n"
                "    return b'220' if response.startswith(b'220') else b''\n"
            )

    chater = Chater()
    producer = AsyncProducer.__new__(AsyncProducer)
    producer.chater = chater
    producer.rfcp = SimpleNamespace(pro_name="ftp")
    producer._primary_response_field_info = lambda: "Reply-Code"
    producer._primary_response_field_name = lambda: "Reply-Code"
    producer._record_generation = lambda *_args, **_kwargs: None
    producer._generated_code_timeout = lambda: 1

    code = asyncio.run(producer._parser_gen_async())

    assert "response.startswith" in code
    assert "Expected non-empty bytes classification" in chater.repair_error
    assert "Reply-Code" in chater.repair_error
    assert sample.hex() in chater.repair_error
    assert chater.generation_kwargs == {
        "pro_name": "ftp", "res_info": "Reply-Code",
    }


def test_parser_generation_prompt_uses_only_response_fields():
    prompt_path = PROJECT_ROOT / "skills" / "builder" / "parser_generation.md"
    chater = AsyncChater.__new__(AsyncChater)
    chater.pmp = SimpleNamespace(
        _tem_gen_parser=Template(prompt_path.read_text(encoding="utf-8"))
    )
    captured = {}

    async def fake_chat_llm(*, prompt, usage):
        captured.update(prompt=prompt, usage=usage)
        return "def packet_parser(response: bytes) -> bytes:\n    return b'200'\n"

    chater.chat_llm = fake_chat_llm
    result = asyncio.run(chater.llm_parser_gen(
        pro_name="http",
        res_info='[{"field_name":"StatusCode"}]',
    ))

    assert result.startswith("def packet_parser")
    assert captured["usage"] == "parser_gen"
    assert "RESPONSE_FIELDS_JSON" in captured["prompt"]
    assert "TYPE_RULES_JSON" not in captured["prompt"]
    assert "Do not map it to an invented semantic label" in captured["prompt"]


def test_all_benchmark_targets_define_decodable_real_parser_samples():
    config = yaml.safe_load(
        (PROJECT_ROOT / "config" / "configs.yaml").read_text(
            encoding="utf-8"
        )
    )
    targets = {
        "lightftp",
        "forked-daapd",
        "bftpd",
        "pureftpd",
        "proftpd",
        "exim",
        "kamailio",
        "live555",
        "lighttpd",
    }

    for target in targets:
        samples = decode_parser_validation_samples(
            config[target]["parser_validation_samples"]
        )
        assert samples
        assert all(samples)
