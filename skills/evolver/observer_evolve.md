TASK
Repair an observer whose same-type responses produced different semantic hashes.

INPUT
PROTOCOL: $pro_name
RESPONSE_TYPE: $response_type
IR_FIELD_TABLE_JSON:
$msg_ir
SAMPLES_AND_HASHES:
$samples
BASE_SHA256: $base_sha256
NUMBERED_BASE_CODE:
$original_code

CONTRACT
Return a complete `packet_observer(response: bytes) -> str`.
- All supplied same-meaning samples must share one lowercase SHA-256 hash.
- Normalize only sample-varying fields that the IR identifies as non-behavioral; preserve their presence with deterministic field-specific markers.
- Preserve status/type, framing, lengths, flags, capabilities, retry values, semantic errors, required fields, and payload structure.
- If parsing is unsafe, hash original bytes. Never raise; built-ins only; no I/O/dynamic execution.

OUTPUT
JSON only. For a change, return {"base_sha256":"$base_sha256","action":"patch","edits":[{"start_line":1,"end_line":1,"replacement":"changed source lines"}]}.
Use {"base_sha256":"$base_sha256","action":"no_change","reason":"already_satisfies_goal|insufficient_evidence|no_safe_change","edits":[]} only when the current observer already maps all supplied same-meaning samples to one digest or no safe evidence-backed normalization exists. Do not use no_change when the samples still diverge.
Line ranges are one-based, inclusive, non-overlapping, and refer to NUMBERED_BASE_CODE. For patch, return only changed ranges, never the full program. Replacement must contain exact Python including indentation and escaped newlines.
