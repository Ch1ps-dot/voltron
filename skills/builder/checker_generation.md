TASK
Generate a conformance checker for one response type.

INPUT
PROTOCOL: $pro_name
RESPONSE_TYPE: $response_type
PRIMARY_FIELDS_JSON:
$res_info
TYPE_RULE_JSON:
$type_rule
IR_FIELD_TABLE_JSON:
$msg_ir

CONTRACT
Define `packet_checker(response: bytes) -> bool`.
- Reject non-bytes, malformed, truncated, other-type, partially matching, and unexplained trailing data; never raise.
- Identify the target from the complete type-rule field combination; use the primary field only when the rule is unusable.
- Parse candidates in wire order with exact byte/bit offsets. Enforce constants, lengths/ranges/enums/grammars, delimiters, dependencies, optionality, repetition, framing, payload boundaries, and whole-message consumption when specified.
- Interpret hex as wire bytes/integers, bit strings as bits for bit-length fields, and quoted text as encoded bytes.
- If multiple IR messages match, accept only a fully conforming candidate.
- Compile all protocol logic into self-contained Python using built-ins only; no I/O/network/subprocess/dynamic execution.

OUTPUT
Executable Python defining `packet_checker` only; no Markdown or prose.
