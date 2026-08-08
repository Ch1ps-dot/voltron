TASK
Repair and evolve a request generator to reach additional legal protocol states.

INPUT
PROTOCOL: $pro_name
TYPE_FIELD: $field_name
REQUEST_TYPE: $msg_type
IR_FIELD_TABLE_JSON:
$msg_ir
BASE_SHA256: $base_sha256
NUMBERED_BASE_GENERATOR:
$code
SUT_CONTEXT:
$info
OBSERVED_TRANSITIONS:
$trace
RELATED_GENERATORS:
$related_code

CONTRACT
Return `generate() -> bytes` with no parameters.
- Diagnose and fix invalid order/values/encoding/framing, missing fields, length/payload errors, or unsatisfied state preconditions evidenced by the inputs.
- Preserve IR structure and SUT compatibility; use related generators only for supported cross-message/state dependencies.
- Vary valid under-tested fields/optional elements toward unobserved legal transitions; output exactly one `$msg_type` message per call.
- Do not invent protocol rules. Self-contained Python built-ins only; no networking; never return non-bytes.

OUTPUT
JSON only. For a change, return {"base_sha256":"$base_sha256","action":"patch","edits":[{"start_line":1,"end_line":1,"replacement":"changed source lines"}]}.
If the existing generator already satisfies the goal, evidence is insufficient, or no safe change exists, return {"base_sha256":"$base_sha256","action":"no_change","reason":"already_satisfies_goal|insufficient_evidence|no_safe_change","edits":[]}.
Line ranges are one-based, inclusive, non-overlapping, and refer to NUMBERED_BASE_GENERATOR. For patch, return only changed ranges, never the full program. Replacement must contain exact Python including indentation and escaped newlines.
