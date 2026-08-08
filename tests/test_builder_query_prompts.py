from pathlib import Path
from string import Template


ROOT = Path(__file__).resolve().parents[1]


def test_field_query_prompts_render_without_unknown_placeholders():
    values = {
        "rfc_num": "rfc-example",
        "pro_name": "demo",
        "rfc_doc": "wire format",
    }

    for name in ("request_query.md", "response_query.md"):
        source = (ROOT / "skills" / "builder" / name).read_text(
            encoding="utf-8",
        )
        rendered = Template(source).substitute(values)

        assert "rfc-example" in rendered
        assert "wire format" in rendered


def test_request_query_keeps_operation_uri_patterns():
    source = (
        ROOT / "skills" / "builder" / "request_query.md"
    ).read_text(encoding="utf-8")

    assert "URI path patterns" in source
    assert "path parameters as placeholders" in source


def test_response_query_excludes_payload_data_type_tags():
    source = (
        ROOT / "skills" / "builder" / "response_query.md"
    ).read_text(encoding="utf-8")

    assert "payload encoding/data-type tags" in source
