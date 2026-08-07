SCOPE
Authorized controlled fuzz testing only.

TASK
Generate one structured mutation that reaches deep parser/state validation and explores an RFC outcome not yet observed.

INPUT
PROTOCOL: $pro_name
TYPE_FIELD: $field_name
REQUEST_TYPE: $msg_type
IR_FIELD_TABLE_JSON:
$msg_ir
SUT_CONTEXT:
$info
BASE_SHA256: $base_sha256
NUMBERED_SAVED_BEST_GENERATOR:
$code
RFC_POSSIBLE_RESPONSES:
$poss_response
RUNTIME_OBSERVED_RESPONSES:
$trace

CONTRACT
Define `mutate() -> bytes` with no parameters.
- Preserve the saved generator's state-reaching structure, then introduce controlled field-level anomalies supported by the IR.
- Prioritize RFC response types not yet present in runtime observations; avoid patterns that only repeat observed outcomes.
- Prefer mutations that pass framing and early parsing before stressing deeper validation: boundary/out-of-range numbers, inconsistent declared lengths, empty/long/invalid tokens, malformed quoting/charset, reused/duplicated IDs, unsupported versions, or compound semantic conflicts.
- Use deterministic mutation families plus bounded randomness, built-ins only, no networking/I/O, and never raise. Keep runtime practical while allowing large free-form payloads when useful.

OUTPUT
JSON only: {"base_sha256":"$base_sha256","edits":[{"start_line":1,"end_line":1,"replacement":"changed source lines"}]}.
Line ranges are one-based, inclusive, non-overlapping, and refer to NUMBERED_SAVED_BEST_GENERATOR. Return only changed ranges, never the full program. Replacement must contain exact Python including indentation and escaped newlines.
