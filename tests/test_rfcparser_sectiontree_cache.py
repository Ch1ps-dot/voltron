import asyncio
import pickle
from pathlib import Path

import pytest

from voltron.configs import configs
from voltron.rfcparser.rfc_parser import AsyncRFCParser
from voltron.rfcparser.setciontree import SectionTree


def make_tree(name: str, content: str = "protocol section") -> SectionTree:
    tree = SectionTree.__new__(SectionTree)
    tree.name = name
    tree.doc_content = content
    tree.leafs = []
    return tree


def make_parser(tmp_path: Path) -> AsyncRFCParser:
    parser = AsyncRFCParser.__new__(AsyncRFCParser)
    parser.tree_path = tmp_path
    parser.tree_dict = {}
    return parser


def test_parser_separates_tree_cache_from_ir(tmp_path, monkeypatch):
    monkeypatch.setattr(configs, "base_path", tmp_path)
    monkeypatch.setattr(configs, "doc_paths", [])
    monkeypatch.setattr(configs, "pro_name", "ftp", raising=False)
    monkeypatch.setattr(configs, "rfc_name", [], raising=False)

    parser = AsyncRFCParser(chater=object())

    assert parser.ir_path == tmp_path / "component" / "ir" / "ftp"
    assert parser.tree_path == tmp_path / "component" / "tree" / "ftp"
    assert parser.ir_path.is_dir()
    assert parser.tree_path.is_dir()


def test_document_annotation_falls_back_after_bounded_attempts():
    parser = AsyncRFCParser.__new__(AsyncRFCParser)
    parser.rfc_name = ["rfc959"]
    parser.pro_name = "ftp"
    calls = []

    class InvalidChater:
        async def llm_doc_parse(self, **kwargs):
            calls.append(kwargs)
            return "invalid"

    parser.chater = InvalidChater()
    tree = make_tree("rfc959", "protocol section")
    from voltron.rfcparser.setciontree import SectionNode

    node = SectionNode(1, 0, len(tree.doc_content), "1. Message")
    tree.leafs = [node]

    asyncio.run(
        parser._spe_parse_one(node, asyncio.Semaphore(1), tree)
    )

    assert len(calls) == parser.ANNOTATION_MAX_ATTEMPTS
    assert node.content_type == "none"


def test_damaged_sectiontree_cache_is_regenerated(tmp_path, monkeypatch):
    parser = make_parser(tmp_path)
    cache_path = tmp_path / "rfc959.pkl"
    cache_path.write_bytes(b"\x80\x05truncated")
    regenerated = make_tree("rfc959")
    calls = []

    def regenerate(idx):
        calls.append(idx)
        parser.tree_dict["rfc959"] = regenerated
        parser.save_st(regenerated)

    monkeypatch.setattr(parser, "spe_parse", regenerate)

    assert parser.prepare_section_tree(3, "rfc959") == "regenerated"
    assert calls == [3]
    assert parser.tree_dict["rfc959"] is regenerated

    with cache_path.open("rb") as stream:
        saved = pickle.load(stream)
    assert isinstance(saved, SectionTree)
    assert saved.name == "rfc959"


def test_valid_sectiontree_cache_is_reused(tmp_path, monkeypatch):
    parser = make_parser(tmp_path)
    tree = make_tree("rfc959")
    parser.save_st(tree)
    monkeypatch.setattr(
        parser,
        "spe_parse",
        lambda idx: pytest.fail("valid cache should not be regenerated"),
    )

    assert parser.prepare_section_tree(0, "rfc959") == "loaded"
    assert parser.tree_dict["rfc959"].name == "rfc959"


def test_legacy_sectiontree_cache_gets_annotation_fields(tmp_path):
    parser = make_parser(tmp_path)
    tree = make_tree("rfc959", "message section")
    from voltron.rfcparser.setciontree import SectionNode

    node = SectionNode(1, 0, len(tree.doc_content), "1. Message")
    delattr(node, "related_request_types")
    delattr(node, "related_response_types")
    tree.leafs = [node]

    cache_path = tmp_path / "rfc959.pkl"
    with cache_path.open("wb") as stream:
        pickle.dump(tree, stream)

    loaded = parser.load_st("rfc959")

    assert loaded.leafs[0].related_request_types == []
    assert loaded.leafs[0].related_response_types == []
    assert loaded.section_type_annotation_req_types == []
    assert loaded.section_type_annotation_res_types == []


def test_wrong_pickle_type_is_regenerated(tmp_path, monkeypatch):
    parser = make_parser(tmp_path)
    cache_path = tmp_path / "rfc959.pkl"
    with cache_path.open("wb") as stream:
        pickle.dump({"not": "a section tree"}, stream)
    regenerated = make_tree("rfc959")

    def regenerate(idx):
        parser.tree_dict["rfc959"] = regenerated
        parser.save_st(regenerated)

    monkeypatch.setattr(parser, "spe_parse", regenerate)

    assert parser.prepare_section_tree(0, "rfc959") == "regenerated"
    assert parser.tree_dict["rfc959"] is regenerated


def test_atomic_save_removes_temporary_file(tmp_path):
    parser = make_parser(tmp_path)
    parser.save_st(make_tree("rfc959"))

    assert (tmp_path / "rfc959.pkl").is_file()
    assert list(tmp_path.glob("*.tmp-*")) == []


def test_parse_section_trees_stops_before_ir_generation(
    tmp_path,
    monkeypatch,
):
    parser = make_parser(tmp_path)
    parser.rfc_name = ["rfc959", "rfc2428"]
    parser.doc_paths = [
        tmp_path / "rfc959.txt",
        tmp_path / "rfc2428.txt",
    ]
    calls = []

    monkeypatch.setattr(
        parser,
        "ensure_rfc_documents",
        lambda: calls.append("download"),
    )
    monkeypatch.setattr(
        parser,
        "prepare_section_tree",
        lambda idx, name: calls.append((idx, name)) or "regenerated",
    )
    parser._query_prepare = lambda name: pytest.fail(
        "standalone SectionTree parsing must not prepare IR queries"
    )
    parser.ir_generation = lambda: pytest.fail(
        "standalone SectionTree parsing must not generate IR"
    )

    assert parser.parse_section_trees() == [
        ("rfc959", "regenerated"),
        ("rfc2428", "regenerated"),
    ]
    assert calls == [
        "download",
        (0, "rfc959"),
        (1, "rfc2428"),
    ]


def test_parse_section_trees_rejects_mismatched_configuration(tmp_path):
    parser = make_parser(tmp_path)
    parser.rfc_name = ["rfc959"]
    parser.doc_paths = []
    parser.ensure_rfc_documents = lambda: None

    with pytest.raises(ValueError, match="different lengths"):
        parser.parse_section_trees()


def test_normal_run_continues_from_section_trees_to_ir_generation(tmp_path):
    parser = make_parser(tmp_path)
    parser.req_doc = {"request section"}
    parser.res_doc = {"response section"}
    parser.all_doc = {"all section"}
    calls = []

    parser.parse_section_trees = lambda: [
        ("rfc959", "loaded"),
        ("rfc2428", "regenerated"),
    ]
    parser._query_prepare = lambda name: calls.append(("query", name))
    parser.rag_init = lambda sections: calls.append(
        ("rag", tuple(sections))
    ) or object()
    parser.ir_generation = lambda: calls.append(("ir",))

    parser.run()

    assert calls[:2] == [
        ("query", "rfc959"),
        ("query", "rfc2428"),
    ]
    assert ("rag", ("request section",)) in calls
    assert ("rag", ("response section",)) in calls
    assert ("rag", ("all section",)) in calls
    assert calls[-1] == ("ir",)
