TASK
Extract fields whose values select a response message type or protocol outcome from RFC context.

INPUT
RFC: $rfc_num
PROTOCOL: $pro_name
SPEC:
$rfc_doc

RULES
- Include message-level status, result, or response-type codes.
- Exclude generic payload encoding/data-type tags unless they select the whole response message.
- Exclude IDs, sequence/transaction values, flags, lengths, names, and payload/state fields.
- Values must be explicitly specified, not inferred from examples.
- Order primary discriminators first. Deduplicate by semantic position/purpose; merge non-conflicting values.

OUTPUT
JSON array only. Each item: {"field_name":"","position":"","explanation":"","value":[]}.
