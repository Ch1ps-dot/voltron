You are an expert Python developer and protocol analyst.

An IR-driven response hasher produced different hashes for multiple responses
of the same response type. Repair it by identifying dynamic fields that vary
without changing protocol behavior.

Protocol: $pro_name
Response type: $response_type

Response IR:
```xml
$msg_ir
```

Current hasher:
```python
$original_code
```

Observed same-type responses and current hashes:
$samples

Return a complete replacement defining:

```python
def packet_hasher(response: bytes) -> str:
```

Requirements:
- Every supplied sample must produce the same lowercase SHA-256 digest.
- Normalize only differences that the IR and samples identify as dynamic and
  unrelated to protocol behavior, such as timestamps, session IDs, nonces,
  generated request IDs, or trace IDs.
- Preserve status/type, framing, lengths, flags, capabilities, retry values,
  semantic error details, required field presence, and payload structure.
- Preserve dynamic field presence with deterministic field-specific markers.
- Hash the original response unchanged when parsing is unsafe.
- Accept bytes, return a deterministic 64-character lowercase SHA-256 string,
  and never raise.
- Use Python built-in libraries only and perform no I/O or dynamic execution.
- Output only executable Python code without Markdown or prose.
