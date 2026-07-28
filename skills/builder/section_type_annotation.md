You are an expert in networking protocols and RFC analysis.

## Your task:

Analyze one specification section from the {$rfc_num} document of the
{$pro_name} protocol. Decide which known request message types and response
message types this section is related to.

## Known request types:

{$request_types}

## Known response types:

{$response_types}

## Existing coarse section label:

{$content_type}

## Specification section:

Section title: {$section_name}

Section content:
{$section_content}

## Classification guidance:

- A section is related to a request type if it describes that request's syntax,
  fields, valid values, payload, construction rules, processing rules,
  preconditions, state effects, examples, or constraints.
- A section is related to a response type if it describes that response's
  syntax, fields, valid values, payload, status/result/reason codes,
  acknowledgement behavior, processing rules, examples, or constraints.
- If a section describes a shared message format or common field encoding that
  applies to many known request or response types, include all known types that
  clearly use that shared structure.
- Use only the known type names listed above. Do not invent new type names.
- If the section is only generally about the protocol and cannot be tied to any
  listed type, return empty arrays.

## Output JSON schema:

{
  "request_types": ["TYPE_A"],
  "response_types": ["TYPE_B"]
}

## Output constraints:

- Output exactly one JSON object.
- Do not wrap the JSON in Markdown.
- `request_types` and `response_types` must be arrays of strings.
- Every returned string must exactly match one known request or response type.
