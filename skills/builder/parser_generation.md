TASK
Generate a response-type classifier.

INPUT
PROTOCOL: $pro_name
RESPONSE_FIELDS_JSON:
$res_info
TYPE_RULES_JSON:
$type_rules

CONTRACT
Define `packet_parser(response: bytes) -> bytes`.
- Locate/decode rule fields from the descriptors and wire encodings they support.
- Match every `field_values` entry; on a complete match return `type_name.encode("utf-8")`.
- If no usable type rule exists, return the raw primary response-state field (legacy fallback).
- For non-bytes, missing/unparseable data, or no match return `b""`; never raise.
- Do not add unsupported protocol assumptions. Use Python built-ins only; self-contained.

OUTPUT
Executable Python only; must define `packet_parser`; no Markdown or prose.
