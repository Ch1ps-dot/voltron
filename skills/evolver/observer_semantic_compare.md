TASK
Decide whether two same-type responses have identical protocol-relevant meaning.

INPUT
PROTOCOL: $pro_name
RESPONSE_TYPE: $response_type
IR_FIELD_TABLE_JSON:
$msg_ir
OLD_RESPONSE: $old_response
NEW_RESPONSE: $new_response

RULES
- Non-semantic only when IR/context supports dynamic timestamps, generated/session/request/trace IDs, nonces, or equivalent serialization.
- Status/type, framing, flags, capabilities, retry values, semantic errors, required-field presence, payload structure, or behavior-changing fields are semantic.
- If evidence is incomplete or ambiguous, return false.

OUTPUT
Exactly one JSON object: {"semantic_equivalent":false,"confidence":0.0,"reason":"short","dynamic_differences":[],"behavioral_differences":[]}.
No Markdown or prose.
