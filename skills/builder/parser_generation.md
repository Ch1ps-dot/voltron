You are an expert Python developer and network protocol analyst.

Your task is to generate Python code that classifies the protocol response
state from the supplied response type rules. When no usable type rule is
available, fall back to extracting the primary response-state field.

## Input

- Protocol name: $pro_name
- Primary response-state field information: $res_info
- Response type rules: $type_rules

`$res_info` is a JSON list containing response field descriptors extracted from
the protocol's response information file. Each descriptor may contain:

- `field_name`: semantic field name
- `position`: where the field appears in the response
- `explanation`: field meaning and encoding details
- `value`: valid or known values

## Required Program

Generate Python code defining:

```python
def packet_parser(response: bytes) -> bytes:
```

The function must:

1. Accept a raw response message as `bytes`.
2. Use `$type_rules` to determine whether one field or a combination of fields
   identifies each response type.
3. Locate and decode the fields needed by the rules using `$res_info`, protocol
   names, positions, explanations, and known values.
4. If a rule's complete `field_values` combination matches the response, return
   that rule's `type_name` encoded as UTF-8 bytes.
5. If no usable type rule is provided, locate the primary response-state field
   and return its raw wire bytes, preserving the legacy behavior.
6. Return `b""` if the response cannot be classified or parsed.
7. Never raise an exception for arbitrary byte input.

## Constraints

- Use Python 3 built-in libraries only.
- Do not hard-code assumptions unsupported by the supplied descriptors,
  `$type_rules`, or common wire encodings implied by them.
- Prefer exact rule matching over partial matching. A rule with multiple
  `field_values` matches only when every listed field matches.
- Input type is `bytes`; output type is `bytes`.
- The generated code must be self-contained and directly executable.

## Output Requirements

- Output only Python code.
- Do not output Markdown fences, explanations, or prose.
- Do not omit `packet_parser`.
