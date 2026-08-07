TASK
Select RFC-supported response types that specifically indicate successful completion of one request.

INPUT
PROTOCOL: $pro_name
REQUEST_TYPE: $current_request
CANDIDATE_RESPONSE_TYPES:
$response_types
SPEC_CONTEXT:
$info

RULES
- Select only candidate types clearly supported as successful outcomes.
- Exclude errors; do not invent types or assume implementation behavior.

OUTPUT
Exactly one JSON object: {"possible_response":["TYPE"]}. No prose.
