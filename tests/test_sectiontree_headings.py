from voltron.rfcparser.setciontree import SectionTree


def leaf_names(tree: SectionTree) -> list[str]:
    return [node.name for node in tree.leafs]


def test_sectiontree_matches_headings_without_trailing_dot():
    content = """
1 Introduction

Intro text.

2 Message Format

Message text.

2.1 Header

Header text.

2.2 Body

Body text.
"""

    tree = SectionTree(name="demo", content=content)

    assert "1 Introduction" in leaf_names(tree)
    assert "2.1 Header" in leaf_names(tree)
    assert "2.2 Body" in leaf_names(tree)
    assert any(
        "Header text." in tree.fetch_node_content(node)
        for node in tree.leafs
        if node.name == "2.1 Header"
    )


def test_sectiontree_does_not_treat_numbered_body_list_as_heading():
    content = """
1. Introduction

The following exchange happens:
1. The client sends a request.
2. The server replies with data.

2. Protocol Messages

Message text.
"""

    tree = SectionTree(name="demo", content=content)
    names = leaf_names(tree)

    assert "1. The client sends a request." not in names
    assert "2. The server replies with data." not in names
    assert "1. Introduction" in names
    assert "2. Protocol Messages" in names


def test_sectiontree_matches_fixed_rfc_section_titles():
    content = """
Abstract

This document defines a protocol.

1. Introduction

Intro text.

Security Considerations

Security text.

IANA Considerations

IANA text.
"""

    tree = SectionTree(name="demo", content=content)
    names = leaf_names(tree)

    assert "Abstract" in names
    assert "1. Introduction" in names
    assert "Security Considerations" in names
    assert "IANA Considerations" in names
