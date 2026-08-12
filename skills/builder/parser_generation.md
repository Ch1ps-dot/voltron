TASK
Generate a response-type classifier.

INPUT
PROTOCOL: $pro_name
RESPONSE_FIELDS_JSON:
$res_info

CONTRACT
Define `packet_parser(response: bytes) -> bytes`.
- Use only RESPONSE_FIELDS_JSON to locate/decode the protocol's primary
  response-state field or fixed primary-field tuple from the wire response.
- Return its canonical, stable, protocol-defined value as UTF-8 bytes (for
  example `b"250"`, `b"404"`, `b"486"`, or a canonical combination such as
  `b"PUBACK:0"`). Do not map it to an invented semantic label.
- Exclude reason phrases, free-form text, dynamic headers/body values,
  timestamps, session identifiers, nonces, lengths, and other volatile data.
- For non-bytes, missing/unparseable data, or no match return `b""`; never raise.
- Do not add unsupported protocol assumptions. Use Python built-ins only; self-contained.

OUTPUT
Executable Python only; must define `packet_parser`; no Markdown or prose.
