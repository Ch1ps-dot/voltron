TASK
Generate one protocol-valid request constructor for fuzzing/state exploration.

INPUT
PROTOCOL: $pro_name
TYPE_FIELD: $field_name
REQUEST_TYPE: $msg_type
TYPE_RULE:
$type_rule
IR_FIELD_TABLE_JSON:
$msg_ir
SUT_CONTEXT:
$info

CONTRACT
Define `generate() -> bytes` with no parameters.
- Serialize fields in IR order. Emit constants exactly; satisfy the complete type-rule combination.
- Honor lengths, ranges, encodings, delimiters, mandatory/optional fields, framing, and cross-field dependencies; compute derived lengths correctly.
- Choose concrete valid variable values. Prefer SUT/config/captured-message values for semantic fields; otherwise vary valid boundary/common values for state exploration.
- Each `generate()` invocation must return exactly one complete `$msg_type` request. Do not concatenate messages, emit a different request type, or return a multi-message sequence.
- Use ASCII unless evidence requires another encoding. Do not add unsupported protocol behavior.
- Self-contained, Python built-ins only, no I/O/network/subprocess; return bytes.

OUTPUT
Executable Python defining `generate` only; no Markdown or outside prose.
