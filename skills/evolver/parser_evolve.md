You are an expert Python developer and network protocol analyst.

Your task is to repair an existing response parser after it fails to parse a
response message, while preserving response classification based on the supplied
response type rules.

## Input

- Protocol name: $pro_name
- Primary response-state field information: $res_info
- Response type rules: $type_rules
- Original parser code:

```python
$original_code
```

- Failed response message: $message

`$res_info` is a JSON list containing response field descriptors extracted from
the protocol response information file.

## Required Modification

Modify `packet_parser(response: bytes) -> bytes` so that it:

1. Uses `$type_rules` to classify responses by complete field combinations when
   such rules are available.
2. Fixes the root cause that prevented parsing `$message`.
3. Preserves compatibility with previously parsable responses.
4. Returns the matched rule's `type_name` encoded as UTF-8 bytes.
5. Falls back to the primary response-state field only when no usable type rule
   is available.
6. Returns `b""` when the response cannot be located, parsed, or classified.
7. Does not raise an exception for arbitrary byte input.

## Constraints

- Use Python 3 built-in libraries only.
- Keep the public function name `packet_parser`.
- Input type is `bytes`; output type is `bytes`.
- Base parsing behavior only on `$res_info`, `$type_rules`, and the failed
  response message.
- Do not add protocol assumptions unsupported by the supplied inputs.

## Output Requirements

- Output only directly executable Python code.
- Do not output Markdown fences, explanations, or prose.
- Do not omit `packet_parser`.
