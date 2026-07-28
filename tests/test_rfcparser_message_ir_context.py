from voltron.rfcparser.rfc_parser import AsyncRFCParser
from voltron.rfcparser.setciontree import SectionNode, SectionTree


def make_parser() -> AsyncRFCParser:
    parser = AsyncRFCParser.__new__(AsyncRFCParser)
    parser.tree_dict = {"mqtt": make_tree()}
    parser.req_doc = {"fallback request context"}
    parser.res_doc = {"fallback response context"}
    parser.all_doc = {"fallback all context"}
    return parser


def make_tree() -> SectionTree:
    content = (
        "CONNECT request format.\n"
        "PUBLISH request format.\n"
        "CONNACK response format.\n"
        "CONNECT to PUBLISH dependency.\n"
        "General security text.\n"
    )
    tree = SectionTree.__new__(SectionTree)
    tree.name = "mqtt"
    tree.doc_content = content

    connect_start = content.index("CONNECT")
    publish_start = content.index("PUBLISH")
    connack_start = content.index("CONNACK")
    dependency_start = content.index("CONNECT to PUBLISH")
    general_start = content.index("General")

    connect = SectionNode(1, connect_start, publish_start, "CONNECT")
    connect.content_type = "request"
    connect.related_request_types = ["CONNECT"]

    publish = SectionNode(1, publish_start, connack_start, "PUBLISH")
    publish.content_type = "request"
    publish.related_request_types = ["PUBLISH"]

    connack = SectionNode(1, connack_start, dependency_start, "CONNACK")
    connack.content_type = "response"
    connack.related_response_types = ["CONNACK"]

    dependency = SectionNode(1, dependency_start, general_start, "Dependency")
    dependency.content_type = "all"
    dependency.related_request_types = ["CONNECT", "PUBLISH"]

    general = SectionNode(1, general_start, len(content), "General")
    general.content_type = "none"

    tree.leafs = [connect, publish, connack, dependency, general]
    return tree


def test_message_ir_context_uses_request_type_annotations():
    parser = make_parser()

    context = parser._message_ir_context("CONNECT", "req")

    assert "CONNECT request format." in context
    assert "PUBLISH request format." not in context
    assert "CONNACK response format." not in context


def test_message_ir_context_uses_response_type_annotations_for_generic_response():
    parser = make_parser()

    context = parser._message_ir_context(
        "response message of mqtt protocol",
        "res",
    )

    assert "CONNACK response format." in context
    assert "CONNECT request format." not in context
    assert "General security text." not in context


def test_message_ir_context_falls_back_to_coarse_sections():
    parser = AsyncRFCParser.__new__(AsyncRFCParser)
    content = "Generic request format."
    tree = SectionTree.__new__(SectionTree)
    tree.name = "demo"
    tree.doc_content = content
    node = SectionNode(1, 0, len(content), "Request")
    node.content_type = "request"
    tree.leafs = [node]
    parser.tree_dict = {"demo": tree}
    parser.req_doc = set()
    parser.res_doc = set()
    parser.all_doc = set()

    context = parser._message_ir_context("UNKNOWN", "req")

    assert context == "Generic request format."


def test_possible_response_context_uses_sectiontree_annotations():
    parser = make_parser()

    context = parser._possible_response_context("CONNECT")

    assert "CONNECT request format." in context
    assert "CONNACK response format." in context
    assert "General security text." not in context


def test_state_dependency_context_uses_sectiontree_annotations():
    parser = make_parser()

    context = parser._state_dependency_context("CONNECT", "PUBLISH")

    assert "CONNECT request format." in context
    assert "PUBLISH request format." in context
    assert "CONNECT to PUBLISH dependency." in context
    assert "CONNACK response format." not in context
