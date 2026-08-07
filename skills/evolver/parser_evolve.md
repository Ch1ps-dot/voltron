TASK
Repair a response parser after one concrete parse/classification failure.

INPUT
PROTOCOL: $pro_name
PRIMARY_FIELDS_JSON:
$res_info
TYPE_RULES_JSON:
$type_rules
FAILED_RESPONSE: $message
BASE_SHA256: $base_sha256
NUMBERED_BASE_CODE:
$original_code

CONTRACT
Return a complete replacement defining `packet_parser(response: bytes) -> bytes`.
- Fix the failed response's root cause while preserving prior valid behavior.
- Match complete type-rule field combinations and return matched `type_name` as UTF-8 bytes.
- Use the primary field only if no usable type rule exists.
- Return `b""` for non-bytes, missing/unparseable data, or no match; never raise.
- Base protocol behavior only on supplied evidence. Python built-ins only.

OUTPUT
JSON only: {"base_sha256":"$base_sha256","edits":[{"start_line":1,"end_line":1,"replacement":"changed source lines"}]}.
Line ranges are one-based, inclusive, non-overlapping, and refer to NUMBERED_BASE_CODE. Return only changed ranges, never the full program. Replacement must contain exact Python including indentation and escaped newlines.
