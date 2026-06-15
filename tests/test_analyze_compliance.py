import base64
import argparse
import asyncio
import json

import pytest

import analyze_compliance as compliance_module
from analyze_compliance import (
    PairRecord,
    SectionRecord,
    build_prompt,
    discover_pair_files,
    load_pair,
    parse_model_result,
    retrieve_sections,
    run,
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


def test_run_updates_visual_progress_for_each_pair(tmp_path, monkeypatch):
    pair_paths = [
        tmp_path / "pair_000000.json",
        tmp_path / "pair_000001.json",
    ]
    for path in pair_paths:
        write_pair(path)

    class FakeProgress:
        def __init__(self, **kwargs):
            self.total = kwargs["total"]
            self.updates = 0
            self.postfixes = []

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def update(self, amount):
            self.updates += amount

        def set_postfix(self, **kwargs):
            self.postfixes.append(kwargs)

    progress_instances = []

    def fake_tqdm(**kwargs):
        progress = FakeProgress(**kwargs)
        progress_instances.append(progress)
        return progress

    fake_tqdm.write = lambda message: None
    monkeypatch.setattr(compliance_module, "tqdm", fake_tqdm)
    monkeypatch.setattr(
        compliance_module,
        "load_target_config",
        lambda sut: {
            "target_name": sut,
            "protocol": "ftp",
            "rfc_names": ["rfc959"],
            "llm": {},
        },
    )
    monkeypatch.setattr(
        compliance_module,
        "discover_pair_files",
        lambda input_path: pair_paths,
    )
    monkeypatch.setattr(
        compliance_module,
        "load_sections",
        lambda protocol, rfc_names: [],
    )
    monkeypatch.setattr(
        compliance_module,
        "AsyncChater",
        lambda *args, **kwargs: object(),
    )

    async def fake_analyze_pair(*args, **kwargs):
        pair = args[2]
        return {
            "source_pair": str(pair.source),
            "analysis": {
                "verdict": "compliant",
                "confidence": 1.0,
                "summary": "ok",
            },
        }

    monkeypatch.setattr(
        compliance_module,
        "analyze_pair",
        fake_analyze_pair,
    )
    args = argparse.Namespace(
        sut="lightftp",
        input=tmp_path,
        output=tmp_path / "analysis",
        top_k=8,
        max_section_chars=6000,
    )

    assert asyncio.run(run(args)) == 0
    assert len(progress_instances) == 1
    progress = progress_instances[0]
    assert progress.total == 2
    assert progress.updates == 2
    assert progress.postfixes[-1] == {
        "verdict": "compliant",
        "completed": 2,
        "failed": 0,
        "refresh": True,
    }
