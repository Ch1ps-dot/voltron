TASK
Map one specification section to known request and response types.

INPUT
RFC: $rfc_num
PROTOCOL: $pro_name
KNOWN_REQUEST_TYPES: $request_types
KNOWN_RESPONSE_TYPES: $response_types
COARSE_LABEL: $content_type
SECTION: $section_name
$section_content

RULES
- Match syntax, fields, values, payload, construction/processing, preconditions, state effects, examples, errors, or shared encodings.
- Return only exact known type names; never invent names.
- Shared format may map to every clearly affected known type. General unrelated text maps to empty arrays.

OUTPUT
Exactly one JSON object: {"request_types":[],"response_types":[]}. No prose.
