You are an expert Python developer and network protocol analyst.

Your task is to generate Python code that extracts the protocol response state
from exactly one state field.

## Input

- Protocol name: $pro_name
- Primary response-state field information: $res_info

`$res_info` is a JSON list containing exactly one field descriptor: the first
state-field descriptor from the protocol's response information file. The
descriptor may contain:

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
2. Locate and extract only the field described by the sole descriptor in
   `$res_info`.
3. Use the descriptor's `position`, `explanation`, and `value` information to
   determine the field's wire location, length, encoding, and boundaries.
4. Return the extracted field value as its raw wire bytes.
5. Return `b""` if the field cannot be located or parsed.
6. Never concatenate the field with another field and never use another response
   field to construct the returned state value.
7. Never raise an exception for arbitrary byte input.

## Constraints

- Use Python 3 built-in libraries only.
- Do not hard-code assumptions unsupported by the supplied descriptor.
- The response state is determined solely by the first state field supplied in
  `$res_info`.
- Input type is `bytes`; output type is `bytes`.
- The generated code must be self-contained and directly executable.

## Output Requirements

- Output only Python code.
- Do not output Markdown fences, explanations, or prose.
- Do not omit `packet_parser`.
