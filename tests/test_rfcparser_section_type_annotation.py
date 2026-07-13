import asyncio
import json
from pathlib import Path

from voltron.rfcparser.rfc_parser import AsyncRFCParser
from voltron.rfcparser.setciontree import SectionNode, SectionTree


class FakeChater:
    async def llm_section_type_annotation(self, **kwargs):
        content = kwargs["section_content"]
        if "CONNECT" in content:
            result = {
                "request_types": ["CONNECT"],
                "response_types": ["CONNACK"],
            }
        else:
            result = {"request_types": [], "response_types": []}
        return "", json.dumps(result)


def make_parser(tmp_path: Path) -> AsyncRFCParser:
    parser = AsyncRFCParser.__new__(AsyncRFCParser)
    parser.ir_path = tmp_path
    parser.chater = FakeChater()
    parser.rfc_name = ["mqtt-v5.0"]
    parser.pro_name = "mqtt"
    parser.req_types = {"CONNECT", "PUBLISH"}
    parser.res_types = {"CONNACK", "PUBACK"}
    return parser


def make_tree() -> SectionTree:
    content = "CONNECT is followed by CONNACK."
    tree = SectionTree.__new__(SectionTree)
    tree.name = "mqtt-v5.0"
    tree.doc_content = content
    node = SectionNode(1, 0, len(content), "3.1 CONNECT")
    node.content_type = "all"
    tree.leafs = [node]
    return tree


def test_section_type_annotation_marks_leaf_nodes_and_saves_cache(tmp_path):
    parser = make_parser(tmp_path)
    tree = make_tree()
    parser.tree_dict = {"mqtt-v5.0": tree}

    asyncio.run(parser._annotate_section_message_types())

    node = tree.leafs[0]
    assert node.related_request_types == ["CONNECT"]
    assert node.related_response_types == ["CONNACK"]
    assert tree.section_type_annotation_req_types == ["CONNECT", "PUBLISH"]
    assert tree.section_type_annotation_res_types == ["CONNACK", "PUBACK"]
    assert (tmp_path / "mqtt-v5.0.pkl").is_file()


def test_section_type_annotation_reuses_current_cache(tmp_path):
    parser = make_parser(tmp_path)
    tree = make_tree()
    tree.leafs[0].related_request_types = ["CONNECT"]
    tree.leafs[0].related_response_types = ["CONNACK"]
    tree.section_type_annotation_req_types = ["CONNECT", "PUBLISH"]
    tree.section_type_annotation_res_types = ["CONNACK", "PUBACK"]
    parser.tree_dict = {"mqtt-v5.0": tree}

    class FailingChater:
        async def llm_section_type_annotation(self, **kwargs):
            raise AssertionError("current annotations should be reused")

    parser.chater = FailingChater()

    asyncio.run(parser._annotate_section_message_types())

    assert tree.leafs[0].related_request_types == ["CONNECT"]
