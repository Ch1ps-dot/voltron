import pickle
from pathlib import Path

import pytest

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
    parser.ir_path = tmp_path
    parser.tree_dict = {}
    return parser


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
