import base64
import argparse
import asyncio
import json
import pickle
from pathlib import Path

import pytest

import analyze_compliance as compliance_module
from analyze_compliance import (
    PairRecord,
    SectionRecord,
    analyze_pair_file,
    build_prompt,
    discover_pair_files,
    generate_vulnerability_report,
    load_pair,
    load_sections,
    load_target_config,
    parse_model_result,
    positive_int,
    retrieve_sections,
    run,
)
from voltron.rfcparser.setciontree import SectionNode, SectionTree


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


def write_section_tree(
    path,
    content="331 User name okay, need password.",
):
    tree = SectionTree.__new__(SectionTree)
    tree.doc_content = content
    node = SectionNode(1, 0, len(content), "4.2 Replies")
    node.content_type = "response"
    tree.leafs = [node]
    with path.open("wb") as stream:
        pickle.dump(tree, stream)


def test_load_sections_skips_truncated_cache_when_another_is_valid(
    tmp_path,
    monkeypatch,
    capsys,
):
    tree_path = tmp_path / "component" / "tree" / "ftp"
    tree_path.mkdir(parents=True)
    (tree_path / "broken.pkl").write_bytes(b"\x80\x05truncated")
    write_section_tree(tree_path / "rfc959.pkl")
    monkeypatch.setattr(compliance_module.configs, "base_path", tmp_path)

    sections = load_sections("ftp", ["broken", "rfc959"])

    assert len(sections) == 1
    assert sections[0].rfc == "rfc959"
    stderr = capsys.readouterr().err
    assert "skipping unusable SectionTree cache" in stderr
    assert "UnpicklingError" in stderr
    assert "Loaded 1 protocol sections" in stderr


def test_load_sections_reports_all_unusable_caches(
    tmp_path,
    monkeypatch,
):
    tree_path = tmp_path / "component" / "tree" / "ftp"
    tree_path.mkdir(parents=True)
    (tree_path / "broken.pkl").write_bytes(b"\x80\x05truncated")
    monkeypatch.setattr(compliance_module.configs, "base_path", tmp_path)

    with pytest.raises(RuntimeError) as error:
        load_sections("ftp", ["broken", "missing"])

    message = str(error.value)
    assert "no usable cached RFC SectionTrees" in message
    assert "broken.pkl" in message
    assert "missing.pkl" in message
    assert "regenerate component/tree caches" in message


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
    assert "quoted/spec-located normative evidence" in prompt


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


def test_concurrency_must_be_positive():
    assert positive_int("4") == 4
    with pytest.raises(argparse.ArgumentTypeError):
        positive_int("0")


def test_load_target_config_uses_compliance_llm(tmp_path, monkeypatch):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "configs.yaml").write_text(
        """
lightftp:
  protocol: ftp
  rfc_name: [rfc959]
llm_doc:
  base_url: https://doc.example
  api_key: doc-key
  model: doc-model
  async_sem: 2
llm_compliance:
  base_url: https://compliance.example
  api_key: compliance-key
  model: compliance-model
  async_sem: 6
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(compliance_module.configs, "base_path", tmp_path)

    target = load_target_config("lightftp")

    assert target["llm"]["model"] == "compliance-model"
    assert compliance_module.configs.base_url_compliance == (
        "https://compliance.example"
    )
    assert compliance_module.configs.api_key_compliance == "compliance-key"
    assert compliance_module.configs.model_compliance == "compliance-model"
    assert compliance_module.configs.async_sem_compliance == 6


@pytest.mark.parametrize(
    "verdict",
    ["compliant", "non_compliant", "uncertain"],
)
def test_analyze_pair_file_groups_results_by_verdict(
    verdict,
    tmp_path,
    monkeypatch,
):
    pair_path = tmp_path / "pair_000000.json"
    write_pair(pair_path)

    async def fake_analyze_pair(*args, **kwargs):
        return {
            "source_pair": str(pair_path),
            "analysis": {
                "verdict": verdict,
                "confidence": 1.0,
                "summary": "test",
            },
        }

    monkeypatch.setattr(
        compliance_module,
        "analyze_pair",
        fake_analyze_pair,
    )
    if verdict == "non_compliant":
        async def fake_report(*args, **kwargs):
            return {
                "json": str(tmp_path / "report.json"),
                "markdown": str(tmp_path / "report.md"),
            }

        monkeypatch.setattr(
            compliance_module,
            "generate_vulnerability_report",
            fake_report,
        )
    output_dir = tmp_path / "analysis"
    _, result, error = asyncio.run(
        analyze_pair_file(
            semaphore=asyncio.Semaphore(1),
            chater=object(),
            target={},
            pair_path=pair_path,
            sections=[],
            output_dir=output_dir,
            top_k=8,
            max_section_chars=6000,
        )
    )

    assert error is None
    assert result["analysis"]["verdict"] == verdict
    assert (
        output_dir
        / verdict
        / "pair_000000.analysis.json"
    ).is_file()


def test_vulnerability_report_includes_request_and_response(tmp_path):
    class FakeChater:
        def __init__(self):
            self.prompt = ""
            self.usage = ""

        async def chat_llm(self, prompt, usage):
            self.prompt = prompt
            self.usage = usage
            return "## Summary\nThe response violates the expected reply."

    pair_path = tmp_path / "pair_000000.json"
    request = b"USER test\r\n"
    response = b"500 unexpected\r\n"
    write_pair(pair_path, request=request, response=response)
    pair = load_pair(pair_path)
    result = {
        "source_pair": str(pair_path),
        "target": "lightftp",
        "protocol": "ftp",
        "request_type": pair.request_type,
        "response_type": pair.response_type,
        "analysis": {
            "verdict": "non_compliant",
            "confidence": 0.92,
            "summary": "Unexpected response for USER.",
            "violations": [],
            "evidence": [],
        },
        "retrieved_sections": [
            {
                "rfc": "rfc959",
                "section": "4.2",
                "content_type": "response",
                "bm25_score": 1.0,
            }
        ],
    }
    chater = FakeChater()

    paths = asyncio.run(
        generate_vulnerability_report(
            chater=chater,
            target={
                "target_name": "lightftp",
                "protocol": "ftp",
                "rfc_names": ["rfc959"],
            },
            pair=pair,
            result=result,
            output_dir=tmp_path / "analysis",
        )
    )

    assert chater.usage == "non_compliance_report"
    assert "USER test" in chater.prompt
    assert "500 unexpected" in chater.prompt
    report_json = json.loads(
        Path(paths["json"]).read_text(encoding="utf-8")
    )
    assert base64.b64decode(report_json["request"]["base64"]) == request
    assert base64.b64decode(report_json["response"]["base64"]) == response
    markdown = Path(paths["markdown"]).read_text(encoding="utf-8")
    assert "USER test" in markdown
    assert "500 unexpected" in markdown
    assert base64.b64encode(request).decode("ascii") in markdown
    assert base64.b64encode(response).decode("ascii") in markdown


def test_non_compliant_analysis_records_report_paths(tmp_path, monkeypatch):
    pair_path = tmp_path / "pair_000000.json"
    write_pair(pair_path)

    class FakeChater:
        async def chat_llm(self, prompt, usage):
            return "## Report\nNon-compliant response."

    async def fake_analyze_pair(*args, **kwargs):
        pair = args[2]
        return {
            "source_pair": str(pair.source),
            "target": "lightftp",
            "protocol": "ftp",
            "request_type": pair.request_type,
            "response_type": pair.response_type,
            "analysis": {
                "verdict": "non_compliant",
                "confidence": 1.0,
                "summary": "bad",
                "violations": [],
                "evidence": [],
            },
            "retrieved_sections": [],
        }

    monkeypatch.setattr(
        compliance_module,
        "analyze_pair",
        fake_analyze_pair,
    )
    output_dir = tmp_path / "analysis"
    _, result, error = asyncio.run(
        analyze_pair_file(
            semaphore=asyncio.Semaphore(1),
            chater=FakeChater(),
            target={
                "target_name": "lightftp",
                "protocol": "ftp",
                "rfc_names": ["rfc959"],
            },
            pair_path=pair_path,
            sections=[],
            output_dir=output_dir,
            top_k=8,
            max_section_chars=6000,
        )
    )

    assert error is None
    assert result["vulnerability_report"]["markdown"].endswith(
        "pair_000000.report.md"
    )
    analysis_path = (
        output_dir
        / "non_compliant"
        / "pair_000000.analysis.json"
    )
    saved = json.loads(analysis_path.read_text(encoding="utf-8"))
    assert "vulnerability_report" in saved
    assert Path(saved["vulnerability_report"]["json"]).is_file()
    assert Path(saved["vulnerability_report"]["markdown"]).is_file()


def test_analyze_pair_file_saves_failures_separately(tmp_path):
    pair_path = tmp_path / "pair_000000.json"
    pair_path.write_text("{broken", encoding="utf-8")
    output_dir = tmp_path / "analysis"

    _, result, error = asyncio.run(
        analyze_pair_file(
            semaphore=asyncio.Semaphore(1),
            chater=object(),
            target={},
            pair_path=pair_path,
            sections=[],
            output_dir=output_dir,
            top_k=8,
            max_section_chars=6000,
        )
    )

    assert result is None
    assert isinstance(error, json.JSONDecodeError)
    failure_path = output_dir / "failed" / "pair_000000.analysis.json"
    failure = json.loads(failure_path.read_text(encoding="utf-8"))
    assert failure["error_type"] == "JSONDecodeError"
    assert failure["source_pair"] == str(pair_path)


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
        concurrency=1,
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
        "concurrency": 1,
        "refresh": True,
    }


def test_run_limits_concurrent_pair_analyses(tmp_path, monkeypatch):
    pair_paths = [
        tmp_path / f"pair_{index:06d}.json"
        for index in range(5)
    ]
    for path in pair_paths:
        write_pair(path)

    class FakeProgress:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def update(self, amount):
            pass

        def set_postfix(self, **kwargs):
            pass

    fake_tqdm = lambda **kwargs: FakeProgress()
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

    active = 0
    max_active = 0

    async def fake_analyze_pair(*args, **kwargs):
        nonlocal active, max_active
        pair = args[2]
        active += 1
        max_active = max(max_active, active)
        await asyncio.sleep(0.01)
        active -= 1
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
        concurrency=2,
    )

    assert asyncio.run(run(args)) == 0
    assert max_active == 2
    assert len(
        list(
            (tmp_path / "analysis" / "compliant").glob(
                "*.analysis.json"
            )
        )
    ) == 5
