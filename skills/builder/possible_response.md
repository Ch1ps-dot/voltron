TASK
Select every RFC-supported server response to one request, including success and error outcomes.

INPUT
PROTOCOL: $pro_name
REQUEST_TYPE: $current_request
CANDIDATE_RESPONSE_TYPES:
$response_types
SPEC_CONTEXT:
$info

RULES
- Select only candidate types clearly supported or implied by the context.
- Do not invent types or assume implementation-specific behavior.

OUTPUT
Exactly one JSON object: {"possible_response":["TYPE"]}. No prose.
