import base64
import json

import pytest

from analyze_compliance import (
    PairRecord,
    SectionRecord,
    build_prompt,
    discover_pair_files,
    load_pair,
    parse_model_result,
    retrieve_sections,
)


def write_pair(path, request=b"USER test\r\n", response=b"331 password\r\n"):
    path.write_text(
        json.dumps(
            {
                "request_type": "USER",
                "response_type": "331",
                "request_length": len(request),
                "response_length": len(response),
                "request": {
                    "encoding": "base64",
                    "data": base64.b64encode(request).decode("ascii"),
                },
                "response": {
                    "encoding": "base64",
                    "data": base64.b64encode(response).decode("ascii"),
                },
            }
        ),
        encoding="utf-8",
    )


def test_discovers_and_loads_pair_from_result_directory(tmp_path):
    pair_dir = tmp_path / "request_response_pairs"
    pair_dir.mkdir()
    pair_path = pair_dir / "pair_000000.json"
    write_pair(pair_path)

    assert discover_pair_files(tmp_path) == [pair_path]
    pair = load_pair(pair_path)
    assert pair.request == b"USER test\r\n"
    assert pair.response == b"331 password\r\n"


def test_rejects_mismatched_pair_length(tmp_path):
    pair_path = tmp_path / "pair_000000.json"
    write_pair(pair_path)
    data = json.loads(pair_path.read_text(encoding="utf-8"))
    data["request_length"] += 1
    pair_path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(ValueError, match="request_length mismatch"):
        load_pair(pair_path)


def test_retrieval_and_prompt_include_exchange_and_rfc_context(tmp_path):
    pair = PairRecord(
        source=tmp_path / "pair_000000.json",
        request_type="USER",
        response_type="331",
        request=b"USER test\r\n",
        response=b"331 password required\r\n",
    )
    sections = [
        SectionRecord(
            rfc="rfc959",
            section="4.1.1 USER",
            content_type="request",
            content="The USER command identifies the user.",
        ),
        SectionRecord(
            rfc="rfc959",
            section="4.2 Replies",
            content_type="response",
            content="331 User name okay, need password.",
        ),
    ]

    retrieved = retrieve_sections(pair, sections, top_k=2)
    prompt = build_prompt(
        {
            "target_name": "lightftp",
            "protocol": "ftp",
            "rfc_names": ["rfc959"],
        },
        pair,
        retrieved,
        max_section_chars=1000,
    )

    assert len(retrieved) == 2
    assert "USER test" in prompt
    assert "331 password required" in prompt
    assert "rfc959" in prompt
    assert "4.2 Replies" in prompt


@pytest.mark.parametrize(
    ("response", "expected"),
    [
        ('{"verdict":"compliant"}', "compliant"),
        ('```json\n{"verdict":"non_compliant"}\n```', "non_compliant"),
        ("not json", "uncertain"),
        ('{"verdict":"unsupported"}', "uncertain"),
    ],
)
def test_parses_model_result(response, expected):
    assert parse_model_result(response)["verdict"] == expected
