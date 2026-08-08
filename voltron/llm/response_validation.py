"""Validate model responses before they enter Voltron's artifact pipeline."""

from __future__ import annotations

import ast
from dataclasses import dataclass, replace
import json
import re
from typing import Any, Literal
from xml.etree import ElementTree

from voltron.configs import configs


ResponseKind = Literal[
    "text",
    "text_enum",
    "json",
    "python",
    "xml",
    "source_delta",
    "ir_delta",
]


class LLMResponseValidationError(ValueError):
    """Raised when a completed LLM call does not contain its promised artifact."""

    def __init__(self, reason: str, detail: str = "") -> None:
        self.reason = reason
        self.detail = detail
        message = reason if not detail else f"{reason}: {detail}"
        super().__init__(message)


@dataclass(frozen=True)
class ResponseContract:
    kind: ResponseKind = "text"
    schema: str = ""
    required_function: str = ""
    allowed_values: frozenset[str] = frozenset()
    allowed_xml_roots: frozenset[str] = frozenset()
    expected_message: str = ""
    allow_markdown_fence: bool = True
    max_chars: int = 100_000


@dataclass(frozen=True)
class ValidatedResponse:
    normalized: str
    parsed: Any = None


_CONTRACTS: dict[str, ResponseContract] = {
    "doc_parse": ResponseContract(
        kind="text_enum",
        allowed_values=frozenset({"request", "response", "all", "none"}),
        allow_markdown_fence=False,
    ),
    "ir_generation": ResponseContract(
        kind="xml",
        allowed_xml_roots=frozenset({"message"}),
    ),
    "ir_repair": ResponseContract(
        kind="xml",
        allowed_xml_roots=frozenset({"message", "ir"}),
    ),
    "ir_evolve": ResponseContract(kind="ir_delta"),
    "generator_gen": ResponseContract(
        kind="python",
        required_function="generate",
    ),
    "code_repair": ResponseContract(kind="python"),
    "generator_evolve": ResponseContract(kind="source_delta"),
    "parser_evolve": ResponseContract(kind="source_delta"),
    "mutator_evolve": ResponseContract(kind="source_delta"),
    "parser_gen": ResponseContract(
        kind="python",
        required_function="packet_parser",
    ),
    "checker_gen": ResponseContract(
        kind="python",
        required_function="packet_checker",
    ),
    "observer_gen": ResponseContract(
        kind="python",
        required_function="packet_observer",
    ),
    "observer_evolve": ResponseContract(kind="source_delta"),
    "checker_evolve": ResponseContract(kind="source_delta"),
    "observer_semantic_compare": ResponseContract(
        kind="json",
        schema="observer_semantic_compare",
    ),
    "req_query": ResponseContract(kind="json", schema="field_query"),
    "res_query": ResponseContract(kind="json", schema="field_query"),
    "req_type_rules": ResponseContract(
        kind="json",
        schema="request_type_rules",
    ),
    "res_type_rules": ResponseContract(
        kind="json",
        schema="response_type_rules",
    ),
    "section_type_annotation": ResponseContract(
        kind="json",
        schema="section_type_annotation",
    ),
    "possible_res": ResponseContract(kind="json", schema="possible_response"),
    "infer_dependency": ResponseContract(kind="json", schema="dependency"),
    "checker_non_compliance_review": ResponseContract(
        kind="json",
        schema="compliance",
    ),
}


def response_contract_for_usage(
    usage: str,
    **overrides: Any,
) -> ResponseContract:
    contract = _CONTRACTS.get(str(usage).strip(), ResponseContract())
    configured_limit = max(
        1,
        int(getattr(configs, "llm_response_max_chars", contract.max_chars)),
    )
    contract = replace(contract, max_chars=configured_limit)
    if overrides:
        contract = replace(contract, **overrides)
    return contract


def _strip_complete_fence(text: str, contract: ResponseContract) -> str:
    match = re.fullmatch(
        r"\s*```(?P<label>[A-Za-z0-9_+-]*)[ \t]*\r?\n"
        r"(?P<body>[\s\S]*?)\r?\n```\s*",
        text,
    )
    if match is None:
        if "```" in text:
            raise LLMResponseValidationError(
                "artifact_with_prose",
                "Markdown fences must enclose the complete response",
            )
        if contract.kind == "python":
            return text
        return text.strip()
    if not contract.allow_markdown_fence:
        raise LLMResponseValidationError(
            "unexpected_markdown_fence",
            "the response contract requires an unfenced value",
        )

    label = match.group("label").lower()
    allowed_labels = {
        "json": {"", "json"},
        "source_delta": {"", "json"},
        "ir_delta": {"", "json"},
        "python": {"", "py", "python"},
        "xml": {"", "xml"},
        "text": {"", "text"},
        "text_enum": {"", "text"},
    }[contract.kind]
    if label not in allowed_labels:
        raise LLMResponseValidationError(
            "wrong_artifact_fence",
            f"expected {contract.kind}, got {label or 'untyped'} fence",
        )
    return match.group("body").strip()


def _require_keys(value: dict[str, Any], keys: set[str], schema: str) -> None:
    missing = sorted(keys - set(value))
    if missing:
        raise LLMResponseValidationError(
            "schema_failure",
            f"{schema} is missing keys: {', '.join(missing)}",
        )


def _string_list(value: Any, field: str) -> list[str]:
    if not isinstance(value, list) or not all(
        isinstance(item, str) for item in value
    ):
        raise LLMResponseValidationError(
            "schema_failure",
            f"{field} must be an array of strings",
        )
    return value


def _validate_json_schema(value: Any, schema: str) -> None:
    if not schema:
        return
    if schema == "field_query":
        if not isinstance(value, list) or not value:
            raise LLMResponseValidationError(
                "schema_failure",
                "field query must be a non-empty JSON array",
            )
        required = {"field_name", "position", "explanation", "value"}
        for index, item in enumerate(value):
            if not isinstance(item, dict) or set(item) != required:
                raise LLMResponseValidationError(
                    "schema_failure",
                    f"field query item {index} must contain exactly {sorted(required)}",
                )
            if not all(isinstance(item[key], str) for key in required - {"value"}):
                raise LLMResponseValidationError(
                    "schema_failure",
                    f"field query item {index} has non-string metadata",
                )
            if not isinstance(item["value"], list):
                raise LLMResponseValidationError(
                    "schema_failure",
                    f"field query item {index}.value must be an array",
                )
        return

    if not isinstance(value, dict):
        raise LLMResponseValidationError(
            "schema_failure",
            f"{schema} must be a JSON object",
        )

    if schema in {"request_type_rules", "response_type_rules"}:
        _require_keys(
            value,
            {"message_direction", "primary_fields", "types"},
            schema,
        )
        expected_direction = schema.removesuffix("_type_rules")
        if value["message_direction"] != expected_direction:
            raise LLMResponseValidationError(
                "schema_failure",
                f"message_direction must be {expected_direction}",
            )
        _string_list(value["primary_fields"], "primary_fields")
        if not isinstance(value["types"], list):
            raise LLMResponseValidationError(
                "schema_failure",
                "types must be an array",
            )
        for index, item in enumerate(value["types"]):
            if not isinstance(item, dict):
                raise LLMResponseValidationError(
                    "schema_failure",
                    f"types[{index}] must be an object",
                )
            _require_keys(
                item,
                {"type_name", "field_values", "explanation"},
                f"types[{index}]",
            )
            if not isinstance(item["type_name"], str) or not item["type_name"].strip():
                raise LLMResponseValidationError(
                    "schema_failure",
                    f"types[{index}].type_name must be non-empty",
                )
            if not isinstance(item["field_values"], dict) or not item["field_values"]:
                raise LLMResponseValidationError(
                    "schema_failure",
                    f"types[{index}].field_values must be a non-empty object",
                )
            if not all(
                isinstance(field_name, str) and str(field_value).strip()
                for field_name, field_value in item["field_values"].items()
            ):
                raise LLMResponseValidationError(
                    "schema_failure",
                    f"types[{index}].field_values contains an empty field",
                )
            if not isinstance(item["explanation"], str):
                raise LLMResponseValidationError(
                    "schema_failure",
                    f"types[{index}].explanation must be a string",
                )
        return

    if schema == "section_type_annotation":
        _require_keys(value, {"request_types", "response_types"}, schema)
        _string_list(value["request_types"], "request_types")
        _string_list(value["response_types"], "response_types")
        return

    if schema == "possible_response":
        _require_keys(value, {"possible_response"}, schema)
        _string_list(value["possible_response"], "possible_response")
        return

    if schema == "dependency":
        _require_keys(value, {"request_dependency", "next_response"}, schema)
        if value["request_dependency"] not in {"dependent", "independent"}:
            raise LLMResponseValidationError(
                "schema_failure",
                "request_dependency must be dependent or independent",
            )
        _string_list(value["next_response"], "next_response")
        return

    if schema == "observer_semantic_compare":
        _require_keys(
            value,
            {
                "semantic_equivalent",
                "confidence",
                "reason",
                "dynamic_differences",
                "behavioral_differences",
            },
            schema,
        )
        if not isinstance(value["semantic_equivalent"], bool):
            raise LLMResponseValidationError(
                "schema_failure",
                "semantic_equivalent must be boolean",
            )
        if not isinstance(value["confidence"], (int, float)) or isinstance(
            value["confidence"], bool
        ) or not 0 <= value["confidence"] <= 1:
            raise LLMResponseValidationError(
                "schema_failure",
                "confidence must be between 0 and 1",
            )
        if not isinstance(value["reason"], str):
            raise LLMResponseValidationError(
                "schema_failure",
                "reason must be a string",
            )
        _string_list(value["dynamic_differences"], "dynamic_differences")
        _string_list(value["behavioral_differences"], "behavioral_differences")
        return

    if schema == "compliance":
        _require_keys(
            value,
            {"verdict", "confidence", "summary", "violations", "evidence"},
            schema,
        )
        if value["verdict"] not in {
            "compliant",
            "non_compliant",
            "uncertain",
        }:
            raise LLMResponseValidationError(
                "schema_failure",
                "invalid compliance verdict",
            )
        if not isinstance(value["confidence"], (int, float)) or isinstance(
            value["confidence"], bool
        ) or not 0 <= value["confidence"] <= 1:
            raise LLMResponseValidationError(
                "schema_failure",
                "compliance confidence must be between 0 and 1",
            )
        if not isinstance(value["summary"], str):
            raise LLMResponseValidationError(
                "schema_failure",
                "compliance summary must be a string",
            )
        if not isinstance(value["violations"], list) or not isinstance(
            value["evidence"], list
        ):
            raise LLMResponseValidationError(
                "schema_failure",
                "compliance violations and evidence must be arrays",
            )
        compliance_items = (
            (
                "violations",
                {"rfc", "section", "requirement", "observation"},
            ),
            ("evidence", {"rfc", "section", "relevance"}),
        )
        for field, keys in compliance_items:
            for index, item in enumerate(value[field]):
                if not isinstance(item, dict):
                    raise LLMResponseValidationError(
                        "schema_failure",
                        f"{field}[{index}] must be an object",
                    )
                _require_keys(item, keys, f"{field}[{index}]")
                if not all(isinstance(item[key], str) for key in keys):
                    raise LLMResponseValidationError(
                        "schema_failure",
                        f"{field}[{index}] fields must be strings",
                    )
        return

    raise LLMResponseValidationError(
        "unknown_schema",
        schema,
    )


def _validate_python(source: str, required_function: str) -> ast.Module:
    try:
        tree = ast.parse(source)
    except SyntaxError as error:
        raise LLMResponseValidationError(
            "invalid_python",
            str(error),
        ) from error
    if required_function:
        functions = [
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == required_function
        ]
        if not functions:
            raise LLMResponseValidationError(
                "missing_function",
                required_function,
            )
    return tree


def _validate_source_delta(value: Any) -> None:
    if not isinstance(value, dict):
        raise LLMResponseValidationError(
            "schema_failure",
            "source delta must be a JSON object",
        )
    _require_keys(value, {"base_sha256", "edits"}, "source delta")
    if not isinstance(value["base_sha256"], str) or not re.fullmatch(
        r"[0-9a-f]{64}", value["base_sha256"]
    ):
        raise LLMResponseValidationError(
            "schema_failure",
            "source delta base_sha256 must be a lowercase SHA-256",
        )
    action = value.get("action", "patch")
    if action not in {"patch", "no_change"}:
        raise LLMResponseValidationError(
            "schema_failure",
            "source delta action must be patch or no_change",
        )
    edits = value["edits"]
    if not isinstance(edits, list) or len(edits) > 64:
        raise LLMResponseValidationError(
            "schema_failure",
            "source delta edits must contain at most 64 edits",
        )
    if action == "patch" and not edits:
        raise LLMResponseValidationError(
            "schema_failure",
            "source delta patch requires 1 to 64 edits",
        )
    if action == "no_change":
        if edits:
            raise LLMResponseValidationError(
                "schema_failure",
                "source delta no_change requires empty edits",
            )
        if value.get("reason") not in {
            "already_satisfies_goal",
            "insufficient_evidence",
            "no_safe_change",
        }:
            raise LLMResponseValidationError(
                "schema_failure",
                "source delta no_change has an invalid reason",
            )
    for index, edit in enumerate(edits):
        if not isinstance(edit, dict):
            raise LLMResponseValidationError(
                "schema_failure",
                f"edits[{index}] must be an object",
            )
        _require_keys(
            edit,
            {"start_line", "end_line", "replacement"},
            f"edits[{index}]",
        )
        start = edit["start_line"]
        end = edit["end_line"]
        replacement = edit["replacement"]
        if (
            not isinstance(start, int)
            or isinstance(start, bool)
            or not isinstance(end, int)
            or isinstance(end, bool)
            or start < 1
            or end < start
            or not isinstance(replacement, str)
        ):
            raise LLMResponseValidationError(
                "schema_failure",
                f"edits[{index}] has an invalid line range or replacement",
            )


def _validate_ir_delta(value: Any) -> None:
    if not isinstance(value, dict):
        raise LLMResponseValidationError(
            "schema_failure",
            "IR delta must be a JSON object",
        )
    _require_keys(value, {"base_sha256", "ops"}, "IR delta")
    if not isinstance(value["base_sha256"], str) or not re.fullmatch(
        r"[0-9a-f]{64}", value["base_sha256"]
    ):
        raise LLMResponseValidationError(
            "schema_failure",
            "IR delta base_sha256 must be a lowercase SHA-256",
        )
    if not isinstance(value["ops"], list) or len(value["ops"]) > 128:
        raise LLMResponseValidationError(
            "schema_failure",
            "IR delta ops must be an array with at most 128 operations",
        )
    if not all(isinstance(operation, dict) for operation in value["ops"]):
        raise LLMResponseValidationError(
            "schema_failure",
            "every IR operation must be an object",
        )


def validate_response(
    response: str | None,
    contract: ResponseContract,
) -> ValidatedResponse:
    if response is None:
        raise LLMResponseValidationError("empty_response", "content is null")
    if not isinstance(response, str):
        raise LLMResponseValidationError(
            "invalid_content_type",
            f"expected string, got {type(response).__name__}",
        )
    if not response.strip():
        raise LLMResponseValidationError("empty_response", "content is blank")
    if len(response) > contract.max_chars:
        raise LLMResponseValidationError(
            "response_too_large",
            f"{len(response)} > {contract.max_chars} characters",
        )

    normalized = _strip_complete_fence(response, contract)
    if not normalized:
        raise LLMResponseValidationError(
            "empty_response",
            "artifact is empty after normalization",
        )

    if contract.kind == "text":
        return ValidatedResponse(normalized)
    if contract.kind == "text_enum":
        normalized = normalized.lower()
        if normalized not in contract.allowed_values:
            raise LLMResponseValidationError(
                "invalid_enum",
                f"expected one of {sorted(contract.allowed_values)}",
            )
        return ValidatedResponse(normalized, normalized)
    if contract.kind in {"json", "source_delta", "ir_delta"}:
        try:
            parsed = json.loads(normalized)
        except json.JSONDecodeError as error:
            raise LLMResponseValidationError(
                "invalid_json",
                str(error),
            ) from error
        if contract.kind == "json":
            _validate_json_schema(parsed, contract.schema)
        elif contract.kind == "source_delta":
            _validate_source_delta(parsed)
        else:
            _validate_ir_delta(parsed)
        return ValidatedResponse(normalized, parsed)
    if contract.kind == "python":
        tree = _validate_python(normalized, contract.required_function)
        return ValidatedResponse(normalized, tree)
    if contract.kind == "xml":
        try:
            root = ElementTree.fromstring(normalized)
        except ElementTree.ParseError as error:
            raise LLMResponseValidationError(
                "invalid_xml",
                str(error),
            ) from error
        if contract.allowed_xml_roots and root.tag not in contract.allowed_xml_roots:
            raise LLMResponseValidationError(
                "invalid_xml_root",
                f"expected {sorted(contract.allowed_xml_roots)}, got {root.tag}",
            )
        if contract.expected_message:
            messages = [root] if root.tag == "message" else list(
                root.findall(".//message")
            )
            if not any(
                message.attrib.get("name") == contract.expected_message
                for message in messages
            ):
                raise LLMResponseValidationError(
                    "missing_message",
                    contract.expected_message,
                )
        return ValidatedResponse(normalized, root)
    raise LLMResponseValidationError(
        "unknown_contract",
        str(contract.kind),
    )
