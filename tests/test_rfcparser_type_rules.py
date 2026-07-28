import asyncio
import json
from pathlib import Path

from voltron.rfcparser.rfc_parser import AsyncRFCParser


def make_parser(tmp_path: Path) -> AsyncRFCParser:
    parser = AsyncRFCParser.__new__(AsyncRFCParser)
    parser.ir_path = tmp_path
    parser.req_doc = set()
    parser.res_doc = set()
    parser.rfc_name = ["rfc-demo"]
    parser.pro_name = "demo"
    parser.chater = None
    return parser


def write_json(path: Path, data):
    path.write_text(json.dumps(data), encoding="utf-8")


def test_key_field_extract_prefers_combined_type_rules(tmp_path):
    parser = make_parser(tmp_path)
    write_json(
        tmp_path / "req.json",
        [
            {
                "field_name": "PacketType",
                "position": "fixed header",
                "explanation": "primary packet type",
                "value": ["PUBLISH"],
            },
            {
                "field_name": "QoS",
                "position": "fixed header flags",
                "explanation": "publish quality of service",
                "value": [0, 1],
            },
        ],
    )
    write_json(
        tmp_path / "res.json",
        [
            {
                "field_name": "StatusCode",
                "position": "first byte",
                "explanation": "response status",
                "value": [200],
            }
        ],
    )
    write_json(
        tmp_path / "req_type_rules.json",
        {
            "message_direction": "request",
            "primary_fields": ["PacketType", "QoS"],
            "types": [
                {
                    "type_name": "PUBLISH_QoS0",
                    "field_values": {"PacketType": "PUBLISH", "QoS": 0},
                    "explanation": "PUBLISH with QoS 0",
                },
                {
                    "type_name": "PUBLISH_QoS1",
                    "field_values": {"PacketType": "PUBLISH", "QoS": 1},
                    "explanation": "PUBLISH with QoS 1",
                },
            ],
        },
    )
    write_json(
        tmp_path / "res_type_rules.json",
        {
            "message_direction": "response",
            "primary_fields": ["StatusCode"],
            "types": [
                {
                    "type_name": "OK",
                    "field_values": {"StatusCode": 200},
                    "explanation": "successful response",
                }
            ],
        },
    )

    asyncio.run(parser.key_field_extract())

    assert parser.req_types == {"PUBLISH_QoS0", "PUBLISH_QoS1"}
    assert parser.res_types == {"OK"}
    assert parser.req_fields == ["PacketType", "QoS"]
    assert parser.res_fields == ["StatusCode"]


def test_key_field_extract_falls_back_to_first_field_values(tmp_path):
    parser = make_parser(tmp_path)
    write_json(
        tmp_path / "req.json",
        [
            {
                "field_name": "Method",
                "position": "first token",
                "explanation": "request method",
                "value": ["GET", "POST"],
            }
        ],
    )
    write_json(
        tmp_path / "res.json",
        [
            {
                "field_name": "StatusCode",
                "position": "first token",
                "explanation": "response status",
                "value": [200, 404],
            }
        ],
    )
    write_json(
        tmp_path / "req_type_rules.json",
        {
            "message_direction": "request",
            "primary_fields": ["Method"],
            "types": [],
        },
    )
    write_json(
        tmp_path / "res_type_rules.json",
        {
            "message_direction": "response",
            "primary_fields": ["StatusCode"],
            "types": [],
        },
    )

    asyncio.run(parser.key_field_extract())

    assert parser.req_types == {"GET", "POST"}
    assert parser.res_types == {"200", "404"}
