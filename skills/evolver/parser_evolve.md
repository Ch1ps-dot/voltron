You are an expert Python developer and network protocol analyst.

Your task is to repair an existing response parser after it fails to parse a
response message, while preserving the rule that response state is extracted
from exactly one field.

## Input

- Protocol name: $pro_name
- Primary response-state field information: $res_info
- Original parser code:

```python
$original_code
```

- Failed response message: $message

`$res_info` is a JSON list containing exactly one descriptor: the first
state-field descriptor from the protocol response information file.

## Required Modification

Modify `packet_parser(response: bytes) -> bytes` so that it:

1. Extracts only the field described by the sole descriptor in `$res_info`.
2. Fixes the root cause that prevented parsing `$message`.
3. Preserves compatibility with previously parsable responses.
4. Returns the selected field's raw wire bytes.
5. Returns `b""` when that field cannot be located or parsed.
6. Does not extract, concatenate, infer, or return any additional response
   field.
7. Does not raise an exception for arbitrary byte input.

## Constraints

- Use Python 3 built-in libraries only.
- Keep the public function name `packet_parser`.
- Input type is `bytes`; output type is `bytes`.
- Base parsing behavior only on the supplied first-field descriptor.
- Do not add protocol assumptions unsupported by `$res_info`.

## Output Requirements

- Output only directly executable Python code.
- Do not output Markdown fences, explanations, or prose.
- Do not omit `packet_parser`.
