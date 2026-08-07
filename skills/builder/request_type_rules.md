TASK
Derive stable request-type rules from candidate discriminators and specification evidence.

INPUT
RFC: $rfc_num
PROTOCOL: $pro_name
CANDIDATE_FIELDS:
$field_info
SPEC:
$rfc_doc

RULES
- Use one field when sufficient; otherwise include the complete discriminator combination.
- Exclude IDs, sequence/transaction values, random tokens, lengths, and payloads unless explicitly defined as operation/type codes.
- Use protocol-defined type names and only supported values. Recover an empty candidate value list only from explicit spec evidence.
- If evidence is unreliable, return an empty `types` array.

OUTPUT
JSON only: {"message_direction":"request","primary_fields":["Field"],"types":[{"type_name":"TYPE","field_values":{"Field":"value"},"explanation":"why"}]}.
Every type requires non-empty `field_values`; no Markdown or prose.
