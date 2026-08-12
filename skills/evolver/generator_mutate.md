SCOPE
Authorized controlled fuzz testing only.

TASK
Generate one structured mutation that reaches deep parser/state validation and explores an RFC outcome not yet observed.

INPUT
PROTOCOL: $pro_name
TYPE_FIELD: $field_name
REQUEST_TYPE: $msg_type
IR_FIELD_TABLE_JSON:
$msg_ir
SUT_CONTEXT:
$info
SAVED_BEST_GENERATOR:
$code
RFC_POSSIBLE_RESPONSES:
$poss_response
RUNTIME_OBSERVED_RESPONSES:
$trace

CONTRACT
The saved baseline is a generator, normally with `generate()` as its entry,
not a mutator. Return a complete, standalone Python program defining exactly
one top-level `mutate() -> bytes` with no parameters. You may reuse or replace
the baseline structure; `generate()` may remain only as a helper and must not
be the only entry point. A minimal safe conversion is:
```python
def generate() -> bytes:
    ...

def mutate() -> bytes:
    return generate()
```
- Before returning, verify that the complete candidate has that one top-level
  `mutate` definition and valid Python.
- Treat SAVED_BEST_GENERATOR as a field-preserving blueprint, not as a fixed
  byte string to return. Reconstruct the one request in `mutate()` on every
  call. Identify each logical field from its construction in the saved code
  and IR_FIELD_TABLE_JSON, then give each mutable field its own bounded random
  value-generation strategy. The result must be a randomized fuzzing packet
  generator, not a short list of hard-coded complete packets.
- Keep mandatory command tokens, field order, separators, framing, and
  state-reaching dependencies needed to make a single `$msg_type` request.
  Randomize the original field-generation methods independently: for example
  select boundary/normal/oversized numeric values; vary optional-field
  presence, repetition, ordering where the protocol permits it, delimiters,
  quoting, escaping, length declarations, identifiers, tokens, strings, and
  payload bytes. Recompute dependent lengths/checksums when retaining valid
  framing; deliberately desynchronize them only as one bounded mutation
  family when the IR supports a declared-length or integrity field.
- Use `random` from the standard library with bounded choices and sizes. Mix
  mostly parseable/state-preserving values with targeted malformed values so
  repeated calls explore both normal and deep validation paths. Do not make
  all fields random when that would break the prerequisite state transition;
  keep those prerequisite constants explicit and randomize the fields they
  enable.
- Each `mutate()` invocation must return exactly one complete `$msg_type` request. Do not concatenate messages, mutate into a different request type, or return a multi-message sequence.
- You may use target-specific URLs or named resources stated in SUT_CONTEXT when helpful for accessing the intended endpoint or resource.
- Prioritize RFC response types not yet present in runtime observations; avoid patterns that only repeat observed outcomes.
- Prefer mutations that pass framing and early parsing before stressing deeper validation: boundary/out-of-range numbers, inconsistent declared lengths, empty/long/invalid tokens, malformed quoting/charset, reused/duplicated IDs, unsupported versions, or compound semantic conflicts.
- Use deterministic mutation families plus bounded randomness, built-ins only, no networking/I/O, and never raise. Keep runtime practical while allowing large free-form payloads when useful.

OUTPUT
Return Python source only, without Markdown fences, JSON, patches, diffs, or
explanation. The source must define `mutate() -> bytes` and return non-empty
bytes on every invocation. Do not return only `generate()`.
