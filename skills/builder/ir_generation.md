TASK
Build protoIR for one protocol message from specification evidence.

INPUT
PROTOCOL: $pro_name
MESSAGE: $message_name
SPEC:
$rfc_doc

PROTOIR CONTRACT
- Root: `<message name="$message_name">`.
- Each ordered field has `name`, `type` (`constant` or `variable`), `length` (`B`, `b`, or `undefined`), and `value`.
- Constants use exact specified wire values; variables use the specified range/grammar/charset.
- Keep wire order. Represent fixed magic/version/flags as constants and identifiers/payloads as variables.
- Put a concise semantic XML comment after each field; note dependencies and justified inferences.
- Do not invent unsupported fields or constraints.

OUTPUT
One well-formed protoIR XML message only; no Markdown or outside prose.
