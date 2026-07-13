import json
from types import SimpleNamespace

from voltron.synthesizer.synthesizer import AsyncProducer


def make_producer() -> AsyncProducer:
    producer = AsyncProducer.__new__(AsyncProducer)
    producer.rfcp = SimpleNamespace(
        req_type_rules={
            "message_direction": "request",
            "primary_fields": ["PacketType", "QoS"],
            "types": [
                {
                    "type_name": "PUBLISH_QoS1",
                    "field_values": {"PacketType": "PUBLISH", "QoS": 1},
                    "explanation": "PUBLISH with QoS 1",
                }
            ],
        },
        res_type_rules={
            "message_direction": "response",
            "primary_fields": ["PacketType", "ReasonCode"],
            "types": [
                {
                    "type_name": "PUBACK_SUCCESS",
                    "field_values": {"PacketType": "PUBACK", "ReasonCode": 0},
                    "explanation": "Successful PUBACK",
                }
            ],
        },
        res_json=[
            {
                "field_name": "PacketType",
                "position": "fixed header",
                "explanation": "response packet type",
                "value": ["PUBACK"],
            },
            {
                "field_name": "ReasonCode",
                "position": "variable header",
                "explanation": "response reason code",
                "value": [0, 16],
            },
        ],
    )
    return producer


def test_producer_exposes_request_type_rule_for_generator():
    producer = make_producer()

    rule = json.loads(producer._request_type_rule_info("PUBLISH_QoS1"))

    assert rule["type_name"] == "PUBLISH_QoS1"
    assert rule["field_values"] == {"PacketType": "PUBLISH", "QoS": 1}


def test_producer_uses_response_type_rules_for_parser_and_checker_state():
    producer = make_producer()

    assert producer._response_types_from_primary_field() == ["PUBACK_SUCCESS"]
    assert producer._primary_response_field_name() == "PacketType+ReasonCode"

    res_info = json.loads(producer._primary_response_field_info())
    assert [field["field_name"] for field in res_info] == [
        "PacketType",
        "ReasonCode",
    ]

    rules = json.loads(producer._response_type_rules_info())
    assert rules["types"][0]["type_name"] == "PUBACK_SUCCESS"


def test_producer_falls_back_to_first_response_field_without_rules():
    producer = make_producer()
    producer.rfcp.res_type_rules = {}

    assert producer._response_types_from_primary_field() == ["PUBACK"]
    assert producer._primary_response_field_name() == "PacketType"
    assert producer._response_type_rule_info("PUBACK") == "{}"
