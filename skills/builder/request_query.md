TASK
Extract fields whose values select a request operation or message type from RFC context.

INPUT
RFC: $rfc_num
PROTOCOL: $pro_name
SPEC:
$rfc_doc

RULES
- Include method/type codes and operation-bearing request targets or URI path patterns.
- Keep path parameters as placeholders when the path shape selects the operation.
- Exclude standalone IDs, sequence/transaction values, flags, lengths, names, and payload/state fields.
- Values must be explicitly specified, not inferred from examples.
- Order primary discriminators first. Deduplicate by semantic position/purpose; merge non-conflicting values.

OUTPUT
JSON array only. Each item: {"field_name":"","position":"","explanation":"","value":[]}.
