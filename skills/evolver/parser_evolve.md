TASK
Repair a response parser after one concrete parse/classification failure.

INPUT
PROTOCOL: $pro_name
PRIMARY_FIELDS_JSON:
$res_info
FAILED_RESPONSE: $message
BASE_SHA256: $base_sha256
NUMBERED_BASE_CODE:
$original_code

CONTRACT
Return a complete replacement defining `packet_parser(response: bytes) -> bytes`.
- Fix the failed response's root cause while preserving prior valid behavior.
- Use only PRIMARY_FIELDS_JSON to extract the canonical, stable, protocol-defined
  primary response-state value. Do not map it to an abstract type name.
- Exclude reason phrases and volatile headers/body values; return only the
  response code or fixed primary-field tuple needed to identify the protocol
  state.
- Return `b""` for non-bytes, missing/unparseable data, or no match; never raise.
- Base protocol behavior only on supplied evidence. Python built-ins only.

OUTPUT
JSON only. For a change, return {"base_sha256":"$base_sha256","action":"patch","edits":[{"start_line":1,"end_line":1,"replacement":"changed source lines"}]}.
Use {"base_sha256":"$base_sha256","action":"no_change","reason":"already_satisfies_goal|insufficient_evidence|no_safe_change","edits":[]} only when the current parser already classifies FAILED_RESPONSE or the supplied evidence cannot support a safe repair. Do not use no_change to hide a still-unclassified response.
Line ranges are one-based, inclusive, non-overlapping, and refer to NUMBERED_BASE_CODE. For patch, return only changed ranges, never the full program. Replacement must contain exact Python including indentation and escaped newlines.
