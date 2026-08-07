TASK
Infer whether the current request semantically depends on the immediately previous request, then select legal next responses.

INPUT
PROTOCOL: $pro_name
PREVIOUS_REQUEST: $last_request
CURRENT_REQUEST: $current_request
CANDIDATE_RESPONSES: $response_types
SPEC:
$rfc_content

RULES
- `dependent` only when the spec says the current request requires state/information established by the previous request or its validity/meaning changes because of it; otherwise `independent`.
- Treat (previous, current, dependency) as the protocol state.
- Select only candidate responses explicitly legal in that state. Exclude unmet preconditions, invalid sequences, ambiguous conditional outcomes, and implementation assumptions.
- If the sequence is invalid or none qualify, return an empty list.

OUTPUT
Exactly one JSON object: {"request_dependency":"dependent|independent","next_response":[]}.
Use one literal dependency value, valid JSON, and no prose.
