TASK
Extract response-discriminating status/result/type code fields from RFC context.

INPUT
RFC: $rfc_num
PROTOCOL: $pro_name
SPEC:
$rfc_doc

RULES
- Include only code-like fields that directly distinguish response types/outcomes.
- Exclude IDs, sequence/transaction values, flags, lengths, names, and payload/state fields.
- Values must be explicitly specified, not inferred/examples. String values must match `^[A-Za-z0-9_]+$`.
- Order primary discriminators first. Deduplicate by semantic position/purpose; merge non-conflicting values.

OUTPUT
JSON array only. Each item: {"field_name":"","position":"","explanation":"","value":[]}.
