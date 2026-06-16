You are an expert Python developer and network protocol analyst.

Generate a self-contained semantic hasher for one response type using the
provided protocol response IR.

## Input

- Protocol: $pro_name
- Target response type: $response_type
- Primary response-state field information: $res_info
- Response IR:

```xml
$msg_ir
```

## Required Program

Define exactly this public function:

```python
def packet_hasher(response: bytes) -> str:
```

The function must parse the response according to the IR, normalize only
dynamic fields that do not change protocol behavior, and return the lowercase
64-character hexadecimal SHA-256 digest of the normalized bytes.

Examples of potentially non-behavioral dynamic fields include message
origination timestamps, generated request IDs, trace IDs, nonces, random
boundaries, session identifiers, and authentication tokens. Exclude or replace
such a value only when its field identity or IR description makes its dynamic,
non-behavioral role clear.

Preserve all fields that can affect protocol behavior or conformance,
including response type/status, framing, lengths, flags, capabilities,
ordering, required headers, retry delays, content types, transfer encodings,
payload structure, and semantic error details. For example, an absolute Date
timestamp may be normalized, but a Retry-After duration or date must be
preserved because it changes behavior.

For text protocols, preserve field names and ordering unless the IR explicitly
states that ordering is irrelevant. Replace a removed value with a stable
field-specific marker so that field presence remains represented. For binary
protocols, preserve framing and stable bytes while replacing only identified
dynamic field bytes with deterministic markers of the same length where
necessary.

If the response cannot be parsed safely or the IR does not identify any
dynamic field, hash the original response unchanged. Never guess by removing
all numbers, opaque values, headers, or payloads.

## Constraints

- Use Python 3 built-in libraries only.
- Import and use `hashlib.sha256`.
- Accept only `bytes`; for any other input, hash `b""`.
- Return a deterministic lowercase 64-character hexadecimal string.
- Never raise for arbitrary input.
- Do not use files, network, subprocesses, or dynamic code execution.
- Compile all IR-specific behavior into the generated program.

## Output

Output only executable Python code without Markdown fences or explanations.
