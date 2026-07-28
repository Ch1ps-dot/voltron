You are an expert in networking protocols and RFC analysis.

## Your task:

Analyze the candidate request-discriminating fields extracted from the
{$rfc_num} document of the {$pro_name} protocol. Determine how request message
types should be identified from one field or a combination of fields.

The goal is to produce stable request type rules that can be used by a fuzzer
to construct and classify request messages.

## Candidate request fields:

{$field_info}

## Request-related specification context:

{$rfc_doc}

## Instructions:

- Use the candidate fields as the primary evidence.
- If one field is sufficient to distinguish request message types, use that
  field alone.
- If multiple fields must be combined to distinguish meaningful request
  subtypes, include all required fields in `field_values`.
- Do not use session IDs, sequence numbers, transaction IDs, packet identifiers,
  random tokens, lengths, or payload values as type discriminators unless the
  specification explicitly defines them as operation/type codes.
- Prefer protocol-defined names for `type_name`, such as GET, CONNECT,
  PUBLISH_QoS1, or equivalent protocol terms.
- Include only values that are explicitly supported by the candidate fields or
  specification context.
- If a candidate field has an empty `value` list but the specification context
  explicitly defines valid values, recover those values from the context.
- If no reliable type rules can be inferred, return an empty `types` array.

## Output JSON schema:

{
  "message_direction": "request",
  "primary_fields": ["field name used first"],
  "types": [
    {
      "type_name": "TYPE_NAME",
      "field_values": {
        "FieldName": "value",
        "OptionalSubtypeField": "value"
      },
      "explanation": "Why this field setting identifies the request type."
    }
  ]
}

## Output constraints:

- Output exactly one JSON object.
- Do not wrap the JSON in Markdown.
- `message_direction` must be `request`.
- `primary_fields` must be an array of strings.
- `types` must be an array.
- Every type must contain `type_name`, `field_values`, and `explanation`.
- Every `field_values` object must contain at least one field-value pair.
