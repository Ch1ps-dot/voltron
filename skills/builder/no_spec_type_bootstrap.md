TASK
Bootstrap a minimal protocol type catalog without RFC text, IR, retrieved
documents, or examples. Use only broadly known protocol behavior.

INPUT
PROTOCOL: $pro_name
TRANSPORT: $transport

OUTPUT
Return JSON only with this exact schema:
{
  "request": {
    "field_name": "request type",
    "types": [
      {"type_name":"TYPE","wire_value":"wire discriminator","explanation":"short"}
    ]
  },
  "response": {
    "field_name": "response type",
    "wire_hint":"stable field or status-line extraction hint",
    "types": [
      {"type_name":"TYPE","wire_value":"wire discriminator","explanation":"short"}
    ]
  }
}

RULES
- Produce a small conservative catalog of stable request and response types.
- `wire_value` must be the actual on-wire discriminator, not an invented label.
- Do not claim RFC evidence or use a response-code whitelist as a validity rule.
- Keep type names and wire values non-empty strings.
