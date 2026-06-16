You are a protocol analyst deciding whether two responses carry the same
protocol-relevant meaning.

Protocol: $pro_name
Response type: $response_type

Response IR:
```xml
$msg_ir
```

Older response:
```text
$old_response
```

New response:
```text
$new_response
```

Determine whether the responses are semantically equivalent for protocol
fuzzing and should therefore receive the same semantic hash.

Treat differences such as timestamps, session IDs, nonces, generated request
IDs, trace IDs, and equivalent serialization details as non-semantic only when
the IR and message context support that conclusion.

Treat differences in status/type, framing, flags, capabilities, retry values,
semantic error details, required field presence, payload structure, or any
field that can change protocol behavior as semantic differences.

Return only one JSON object with this exact shape:

```json
{
  "semantic_equivalent": true,
  "confidence": 0.95,
  "reason": "short explanation",
  "dynamic_differences": ["field or difference"],
  "behavioral_differences": []
}
```

Use `semantic_equivalent: true` only when the protocol-relevant meaning is the
same. If evidence is incomplete or ambiguous, return `false`.
