TASK
Generate a semantic observer for one response type.

INPUT
PROTOCOL: $pro_name
RESPONSE_TYPE: $response_type
PRIMARY_FIELDS_JSON:
$res_info
IR_FIELD_TABLE_JSON:
$msg_ir

CONTRACT
Define `packet_observer(response: bytes) -> str` returning lowercase SHA-256 hex.
- Normalize only IR-identified dynamic, non-behavioral values (for example timestamps, generated IDs, nonces, session/auth/trace tokens), using stable field-specific markers that preserve presence and required length.
- Preserve status/type, framing, lengths, flags, capabilities, ordering, required headers, retry values, encodings, payload structure, and semantic errors.
- Never broadly strip numbers, opaque data, headers, or payloads. If parsing is unsafe or no dynamic field is identified, hash the original bytes.
- Non-bytes are treated as `b""`; never raise. Use built-ins and `hashlib.sha256`; self-contained; no I/O/network/subprocess/dynamic execution.

OUTPUT
Executable Python defining `packet_observer` only; no Markdown or prose.
