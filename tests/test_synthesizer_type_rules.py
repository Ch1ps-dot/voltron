import json
from types import SimpleNamespace

from lxml import etree

from voltron.analyzer.analyzer import analyzer
from voltron.configs import configs
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
        pro_name="mqtt",
        ir_path=None,
        _message_ir_context=lambda msg_type, field_type: "section context",
    )
    producer.req_ir = etree.fromstring(
        b"""
        <ir>
          <message name="CONNECT"><field name="PacketType"/></message>
          <message name="PUBLISH_QoS1"><field name="QoS"/></message>
        </ir>
        """
    )
    producer.res_ir = etree.fromstring(
        b"""
        <ir>
          <message name="PUBACK_SUCCESS"><field name="PacketType"/></message>
        </ir>
        """
    )
    producer._ir_evolution_rounds = {}
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


def test_producer_selects_request_ir_for_generator_evolution():
    producer = make_producer()

    msg_ir = producer._request_ir_info("PUBLISH_QoS1")

    assert '<message name="PUBLISH_QoS1">' in msg_ir
    assert '<field name="QoS"/>' in msg_ir
    assert '<message name="CONNECT">' not in msg_ir


def test_producer_falls_back_to_full_request_ir_when_message_missing():
    producer = make_producer()

    msg_ir = producer._request_ir_info("UNKNOWN")

    assert '<message name="CONNECT">' in msg_ir
    assert '<message name="PUBLISH_QoS1">' in msg_ir


def test_ir_evolution_is_limited_to_model_learning_phase():
    producer = make_producer()
    old_phase = analyzer.active_phase
    old_enabled = configs.ir_evolution_enabled
    old_spec = configs.spec_knowledge
    try:
        configs.ir_evolution_enabled = True
        configs.spec_knowledge = True
        analyzer.active_phase = "model_learning"

        assert producer._ir_evolution_allowed()

        analyzer.active_phase = "fuzzing"
        assert not producer._ir_evolution_allowed()

        analyzer.active_phase = "model_learning"
        configs.spec_knowledge = False
        assert not producer._ir_evolution_allowed()
    finally:
        analyzer.active_phase = old_phase
        configs.ir_evolution_enabled = old_enabled
        configs.spec_knowledge = old_spec


def test_replace_request_ir_preserves_cache_compatibility(tmp_path):
    producer = make_producer()
    producer.rfcp.ir_path = tmp_path

    producer._replace_request_ir(
        "PUBLISH_QoS1",
        '<message name="PUBLISH_QoS1"><field name="PacketType"/>'
        '<field name="NewLength"/></message>',
    )

    msg_ir = producer._request_ir_info("PUBLISH_QoS1")
    assert '<field name="NewLength"/>' in msg_ir
    assert '<field name="QoS"/>' not in msg_ir
    assert producer.rfcp.req_ir.getroot() is producer.req_ir
    assert (tmp_path / "req_ir.xml").is_file()


def test_replace_response_ir_writes_full_response_ir(tmp_path):
    producer = make_producer()
    producer.rfcp.ir_path = tmp_path

    producer._replace_response_ir(
        '<ir><message name="PUBACK_SUCCESS"><field name="ReasonCode"/>'
        '</message></ir>',
    )

    res_ir = etree.tostring(
        producer.res_ir,
        encoding="utf-8",
        pretty_print=True,
    ).decode("utf-8")
    assert '<field name="ReasonCode"/>' in res_ir
    assert producer.rfcp.res_ir.getroot() is producer.res_ir
    assert (tmp_path / "res_ir.xml").is_file()


def test_ir_evolution_round_limit_defaults_to_one():
    producer = make_producer()
    old_max = configs.ir_evolution_max_rounds_per_type
    try:
        configs.ir_evolution_max_rounds_per_type = 1

        assert producer._ir_evolution_round_available(
            "request",
            "PUBLISH_QoS1",
        )
        producer._record_ir_evolution_round("request", "PUBLISH_QoS1")
        assert not producer._ir_evolution_round_available(
            "request",
            "PUBLISH_QoS1",
        )
    finally:
        configs.ir_evolution_max_rounds_per_type = old_max
