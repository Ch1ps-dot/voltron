You are an expert Python developer and network protocol conformance analyst.

Your task is to generate a self-contained Python program that validates a raw
response message against an intermediate representation (IR) extracted from a
protocol specification.

## Input

- Protocol name: $pro_name
- Target response type: $response_type
- Primary response-state field information: $res_info
- Response-message IR:

```xml
$msg_ir
```

The IR is the source of wire-format and conformance constraints. The supplied
primary state-field descriptor and target value are the source of checker type
identity. The IR may define one or more response message types. A message
contains ordered `field` elements and may also contain comments that clarify
field syntax, optionality, dependencies, or semantic constraints.
Typical field attributes include:

- `name`: field name
- `type`: `constant` or `variable`
- `length`: a fixed bit/byte length, a length derived from another field,
  `remaining bytes`, or `undefined`
- `value`: an exact value, range, enumeration, grammar, or textual description

`$res_info` contains exactly the first response-state field descriptor from the
protocol response information file. `$response_type` is one value from that
descriptor's `value` list. Generate a checker specifically for that response
type. The IR remains the source of message layout and conformance constraints;
the state-field descriptor determines which response type this checker accepts.

## Required Program

Generate Python code defining exactly this public function:

```python
def packet_checker(response: bytes) -> bool:
```

The function must return `True` only when the complete response both represents
the target response type `$response_type` according to the primary state field
and conforms to the supplied IR. It must return `False` for other response
types, malformed, truncated, or non-conforming responses and must never raise
an exception for arbitrary byte input.

## Validation Requirements

1. Reject non-`bytes` input and handle an empty response according to the IR.
2. Locate the primary state field described by `$res_info` and require its
   decoded value to equal `$response_type`. Do not assume the response type
   solely from the XML `message` name.
3. Parse fields in wire order. Maintain exact byte and, when required, bit
   offsets so that packed sub-byte fields are validated correctly.
4. Validate every field described by the selected message definition:
   - constants must equal their specified wire value;
   - fixed-length fields must contain exactly the required number of bits or
     bytes;
   - numeric fields must satisfy specified ranges or enumerations;
   - text, token, delimiter, and grammar constraints must be checked when the IR
     provides enough information;
   - lengths derived from earlier fields must be enforced;
   - `remaining bytes` fields must consume the appropriate remainder;
   - optional fields may be absent only when the IR or its comments explicitly
     mark them optional or conditional.
5. Enforce relationships stated in the IR or comments, including payload
   markers, body-presence rules, count/length dependencies, mutually exclusive
   fields, and framing or terminator requirements.
6. For variable-length or `undefined` fields, derive boundaries from the IR's
   delimiters, subsequent constant fields, container grammar, length fields, or
   protocol structure described in the IR. Do not accept a field merely because
   its boundary is inconvenient to parse.
7. For structured aggregate fields such as header sections, option sequences,
   chunks, or repeated records, validate their internal framing and syntax when
   that structure is described by the IR.
8. Require the whole response to be consumed unless the selected IR definition
   explicitly assigns the remainder to a payload/body field. Reject unexplained
   trailing bytes.
9. When multiple message definitions could match, validate each candidate and
   return `True` only if at least one candidate fully conforms. A partial match
   is not sufficient.
10. Interpret common IR value notation accurately:
    - `0x...` denotes hexadecimal wire bytes or integers as appropriate;
    - bit strings such as `01` denote the specified bits, not ASCII digits,
      when the field length is expressed in bits;
    - quoted text denotes encoded text bytes, normally ASCII unless stated
      otherwise;
    - ranges and enumerations constrain the decoded field value.

## Implementation Constraints

- Use Python 3 and built-in libraries only.
- The generated program must be self-contained and deterministic.
- Compile the supplied IR into validation logic in the generated code; the
  function must not require the IR as a runtime argument.
- Compile `$response_type` into the checker. Do not accept another value of the
  primary response-state field.
- Base all protocol-specific behavior on the supplied IR. Do not invent fields,
  defaults, optionality, or constraints not supported by it.
- Prefer small private helper functions when they make bounds checks, bit
  extraction, numeric decoding, or candidate validation clearer.
- Catch malformed-input conditions internally and return `False`.
- Do not perform network, file-system, subprocess, or dynamic code-execution
  operations.

## Output Requirements

- Output only directly executable Python code.
- Do not output Markdown fences, explanations, tests, examples, or prose.
- Do not omit `packet_checker`.
